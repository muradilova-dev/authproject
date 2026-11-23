from captcha.models import CaptchaStore
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


def new_captcha():
    """Создаёт капчу в базе и возвращает (ключ, правильный ответ)."""
    key = CaptchaStore.generate_key()
    return key, CaptchaStore.objects.get(hashkey=key).response


class RegistrationTests(TestCase):
    """Тесты регистрации"""

    url = reverse('accounts:register')

    def data(self, **kw):
        d = {'username': 'ramina', 'email': 'ramina@example.com',
             'password1': 'StrongPass_123', 'password2': 'StrongPass_123'}
        d.update(kw)
        return d

    def test_register_page_opens(self):
        """Страница регистрации открывается (код 200)"""
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_register_success(self):
        """Корректные данные: пользователь создан, выполнен вход, редирект в кабинет"""
        r = self.client.post(self.url, self.data())
        self.assertRedirects(r, reverse('accounts:profile'))
        self.assertTrue(User.objects.filter(username='ramina').exists())
        self.assertIn('_auth_user_id', self.client.session)

    def test_register_password_mismatch(self):
        """Пароли не совпадают: пользователь не создаётся"""
        r = self.client.post(self.url, self.data(password2='Other_pass_999'))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username='ramina').exists())

    def test_register_duplicate_username(self):
        """Имя пользователя уже занято: ошибка формы"""
        User.objects.create_user('ramina', 'a@a.com', 'StrongPass_123')
        r = self.client.post(self.url, self.data(email='new@example.com'))
        self.assertEqual(User.objects.filter(username='ramina').count(), 1)
        self.assertTrue(r.context['form'].errors.get('username'))

    def test_register_duplicate_email(self):
        """Email уже используется: ошибка формы"""
        User.objects.create_user('other', 'ramina@example.com', 'StrongPass_123')
        r = self.client.post(self.url, self.data())
        self.assertTrue(r.context['form'].errors.get('email'))
        self.assertFalse(User.objects.filter(username='ramina').exists())

    def test_register_weak_password(self):
        """Слишком простой пароль отклоняется"""
        r = self.client.post(self.url, self.data(password1='12345678', password2='12345678'))
        self.assertTrue(r.context['form'].errors.get('password2'))

    def test_register_empty_fields(self):
        """Пустая форма: ошибки по всем обязательным полям"""
        r = self.client.post(self.url, {})
        self.assertEqual(User.objects.count(), 0)
        for f in ('username', 'email', 'password1', 'password2'):
            self.assertIn(f, r.context['form'].errors)

    def test_register_redirects_if_authenticated(self):
        """Авторизованного пользователя со страницы регистрации перенаправляет в кабинет"""
        u = User.objects.create_user('u1', 'u1@a.com', 'StrongPass_123')
        self.client.force_login(u)
        self.assertRedirects(self.client.get(self.url), reverse('accounts:profile'))


class LoginCaptchaTests(TestCase):
    """Тесты авторизации и капчи"""

    url = reverse('accounts:login')

    def setUp(self):
        self.user = User.objects.create_user('ramina', 'ramina@example.com', 'StrongPass_123')

    def test_login_page_has_captcha(self):
        """На странице входа есть поле капчи и картинка"""
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertIn('captcha', r.context['form'].fields)
        self.assertContains(r, 'captcha/image/')

    def test_captcha_image_is_served(self):
        """Картинка капчи загружается (image/png)"""
        key, _ = new_captcha()
        r = self.client.get(reverse('captcha-image', args=[key]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'image/png')

    def test_login_success_with_correct_captcha(self):
        """Верный логин, пароль и капча: вход выполнен"""
        key, answer = new_captcha()
        r = self.client.post(self.url, {'username': 'ramina', 'password': 'StrongPass_123',
                                        'captcha_0': key, 'captcha_1': answer})
        self.assertRedirects(r, reverse('accounts:profile'))
        self.assertIn('_auth_user_id', self.client.session)

    def test_login_fails_with_wrong_captcha(self):
        """Верный пароль, но неверная капча: вход запрещён"""
        key, _ = new_captcha()
        r = self.client.post(self.url, {'username': 'ramina', 'password': 'StrongPass_123',
                                        'captcha_0': key, 'captcha_1': 'WRONG'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('captcha', r.context['form'].errors)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_fails_with_empty_captcha(self):
        """Капча не заполнена: вход запрещён"""
        key, _ = new_captcha()
        r = self.client.post(self.url, {'username': 'ramina', 'password': 'StrongPass_123',
                                        'captcha_0': key, 'captcha_1': ''})
        self.assertIn('captcha', r.context['form'].errors)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_fails_without_captcha_fields(self):
        """Запрос без полей капчи (обход формы): вход запрещён"""
        r = self.client.post(self.url, {'username': 'ramina', 'password': 'StrongPass_123'})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_fails_with_wrong_password_correct_captcha(self):
        """Верная капча, неверный пароль: вход запрещён"""
        key, answer = new_captcha()
        r = self.client.post(self.url, {'username': 'ramina', 'password': 'bad_password',
                                        'captcha_0': key, 'captcha_1': answer})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_captcha_is_one_time(self):
        """Капчу нельзя использовать повторно после успешной проверки"""
        key, answer = new_captcha()
        data = {'username': 'ramina', 'password': 'StrongPass_123',
                'captcha_0': key, 'captcha_1': answer}
        self.client.post(self.url, data)
        self.client.post(reverse('accounts:logout'))
        r = self.client.post(self.url, data)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_case_insensitive_captcha(self):
        """Капча не зависит от регистра букв"""
        key, answer = new_captcha()
        r = self.client.post(self.url, {'username': 'ramina', 'password': 'StrongPass_123',
                                        'captcha_0': key, 'captcha_1': answer.swapcase()})
        self.assertRedirects(r, reverse('accounts:profile'))


class ProfileTests(TestCase):
    """Тесты личного кабинета"""

    url = reverse('accounts:profile')

    def setUp(self):
        self.user = User.objects.create_user('ramina', 'ramina@example.com', 'StrongPass_123')

    def test_profile_requires_login(self):
        """Аноним перенаправляется на страницу входа"""
        r = self.client.get(self.url)
        self.assertRedirects(r, f"{reverse('accounts:login')}?next={self.url}")

    def test_profile_shows_user_data(self):
        """Кабинет показывает логин и email пользователя"""
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ramina')
        self.assertContains(r, 'ramina@example.com')

    def test_logout(self):
        """Выход из аккаунта: сессия очищена, кабинет снова закрыт"""
        self.client.force_login(self.user)
        r = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(r, reverse('accounts:login'))
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_full_flow_register_logout_login_profile(self):
        """Полный сценарий: регистрация -> выход -> вход с капчей -> кабинет"""
        self.client.post(reverse('accounts:register'), {
            'username': 'newuser', 'email': 'new@example.com',
            'password1': 'StrongPass_123', 'password2': 'StrongPass_123'})
        self.client.post(reverse('accounts:logout'))
        key, answer = new_captcha()
        self.client.post(reverse('accounts:login'), {
            'username': 'newuser', 'password': 'StrongPass_123',
            'captcha_0': key, 'captcha_1': answer})
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'newuser')
