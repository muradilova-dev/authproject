"""Запуск тестов и сохранение результатов в Word-файл.

Использование:  python manage.py test_report
"""
import io
import time
import unittest
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.test.runner import DiscoverRunner
from django.test.utils import get_runner

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

GROUPS = {
    'RegistrationTests': 'Регистрация',
    'LoginCaptchaTests': 'Авторизация и капча',
    'ProfileTests': 'Личный кабинет',
}


class ReportResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.rows = []
        self._start = 0

    def startTest(self, test):
        self._start = time.perf_counter()
        super().startTest(test)

    def _add(self, test, status, details=''):
        doc = (test._testMethodDoc or '').strip().split('\n')[0]
        self.rows.append({
            'group': GROUPS.get(type(test).__name__, type(test).__name__),
            'name': test._testMethodName,
            'doc': doc,
            'status': status,
            'time': time.perf_counter() - self._start,
            'details': details,
        })

    def addSuccess(self, test):
        super().addSuccess(test)
        self._add(test, 'ПРОЙДЕН')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._add(test, 'ПРОВАЛЕН', self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._add(test, 'ОШИБКА', self._exc_info_to_string(err, test))


def shade(cell, color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), color)
    tcPr.append(shd)


def set_cell(cell, text, bold=False, color=None, size=10, align=None):
    cell.text = ''
    p = cell.paragraphs[0]
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    if align:
        p.alignment = align


class Command(BaseCommand):
    help = 'Запускает тесты приложения accounts и сохраняет отчёт в Word (.docx)'

    def handle(self, *args, **options):
        runner_cls = get_runner(settings)
        runner = runner_cls(verbosity=0, interactive=False)
        suite = runner.build_suite(['accounts'])
        runner.setup_test_environment()
        old_config = runner.setup_databases()
        started = datetime.now()
        t0 = time.perf_counter()
        try:
            result = unittest.TextTestRunner(
                resultclass=ReportResult, verbosity=0,
                stream=io.StringIO()).run(suite)
        finally:
            runner.teardown_databases(old_config)
            runner.teardown_test_environment()
        total_time = time.perf_counter() - t0

        path = self.build_docx(result, started, total_time)
        self.stdout.write(self.style.SUCCESS(
            f'Тестов: {result.testsRun}, ошибок: {len(result.errors)}, '
            f'провалов: {len(result.failures)}'))
        self.stdout.write(self.style.SUCCESS(f'Отчёт сохранён: {path}'))

    def build_docx(self, result, started, total_time):
        order = list(GROUPS.values())
        rows = sorted(result.rows, key=lambda r: order.index(r['group']) if r['group'] in order else 99)
        passed = sum(r['status'] == 'ПРОЙДЕН' for r in rows)
        failed = len(rows) - passed

        doc = Document()
        sec = doc.sections[0]
        sec.left_margin = sec.right_margin = Cm(2)
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)

        h = doc.add_heading('Отчёт о тестировании', level=0)
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p = doc.add_paragraph('Регистрация, авторизация с капчей и личный кабинет (Django)')
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_heading('1. Общая информация', level=1)
        doc.add_paragraph(
            'В проекте на Django реализованы регистрация, вход с капчей '
            '(библиотека django-simple-captcha) и личный кабинет. Тесты написаны '
            'на встроенном django.test.TestCase и запускаются командой '
            'python manage.py test_report, которая сама формирует этот Word-файл.')
        info = [
            ('Дата и время запуска', started.strftime('%d.%m.%Y %H:%M:%S')),
            ('Версия Django', __import__('django').get_version()),
            ('Всего тестов', str(len(rows))),
            ('Пройдено', str(passed)),
            ('Провалено / ошибок', str(failed)),
            ('Время выполнения', f'{total_time:.2f} с'),
            ('Итог', 'ВСЕ ТЕСТЫ ПРОЙДЕНЫ' if not failed else 'ЕСТЬ ПРОВАЛЕННЫЕ ТЕСТЫ'),
        ]
        t = doc.add_table(rows=0, cols=2)
        t.style = 'Table Grid'
        for k, v in info:
            c = t.add_row().cells
            set_cell(c[0], k, bold=True, size=11)
            shade(c[0], 'EEEEEE')
            set_cell(c[1], v, size=11)

        doc.add_heading('2. Сводка по группам', level=1)
        t = doc.add_table(rows=1, cols=4)
        t.style = 'Table Grid'
        for i, name in enumerate(('Группа', 'Всего', 'Пройдено', 'Провалено')):
            set_cell(t.rows[0].cells[i], name, bold=True, size=11,
                     align=WD_ALIGN_PARAGRAPH.CENTER)
            shade(t.rows[0].cells[i], 'D9E2F3')
        for g in GROUPS.values():
            gr = [r for r in rows if r['group'] == g]
            ok = sum(r['status'] == 'ПРОЙДЕН' for r in gr)
            c = t.add_row().cells
            set_cell(c[0], g, size=11)
            for i, val in enumerate((len(gr), ok, len(gr) - ok), start=1):
                set_cell(c[i], str(val), size=11, align=WD_ALIGN_PARAGRAPH.CENTER)

        doc.add_heading('3. Подробные результаты', level=1)
        t = doc.add_table(rows=1, cols=5)
        t.style = 'Table Grid'
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        widths = (Cm(0.9), Cm(3.0), Cm(7.6), Cm(2.8), Cm(1.7))
        for i, name in enumerate(('№', 'Группа', 'Что проверяется', 'Результат', 'Время, с')):
            set_cell(t.rows[0].cells[i], name, bold=True, size=10,
                     align=WD_ALIGN_PARAGRAPH.CENTER)
            shade(t.rows[0].cells[i], 'D9E2F3')
        for n, r in enumerate(rows, 1):
            c = t.add_row().cells
            ok = r['status'] == 'ПРОЙДЕН'
            set_cell(c[0], str(n), align=WD_ALIGN_PARAGRAPH.CENTER)
            set_cell(c[1], r['group'])
            set_cell(c[2], f"{r['doc']}\n({r['name']})")
            set_cell(c[3], r['status'], bold=True, color='1B7F3B' if ok else 'B00020',
                     align=WD_ALIGN_PARAGRAPH.CENTER)
            shade(c[3], 'E6F4EA' if ok else 'FDE7E9')
            set_cell(c[4], f"{r['time']:.2f}", align=WD_ALIGN_PARAGRAPH.CENTER)
        t.autofit = False
        for w, col in zip(widths, t.columns):
            col.width = w
        for row in t.rows:
            for w, cell in zip(widths, row.cells):
                cell.width = w

        bad = [r for r in rows if r['status'] != 'ПРОЙДЕН']
        if bad:
            doc.add_heading('4. Детали ошибок', level=1)
            for r in bad:
                doc.add_paragraph(f"{r['name']}: {r['status']}", style='List Bullet')
                code = doc.add_paragraph(r['details'])
                for run in code.runs:
                    run.font.name = 'Consolas'
                    run.font.size = Pt(8)
        else:
            doc.add_heading('4. Вывод', level=1)
            doc.add_paragraph(
                'Все проверки прошли успешно. Регистрация создаёт пользователя и '
                'отклоняет неверные данные. Вход возможен только при правильных '
                'логине, пароле и капче: неверная, пустая, отсутствующая или '
                'повторно использованная капча вход блокирует. Личный кабинет '
                'доступен только авторизованным пользователям.')

        out_dir = settings.REPORTS_DIR
        out_dir.mkdir(exist_ok=True)
        path = out_dir / 'test_report.docx'
        doc.save(path)
        return path
