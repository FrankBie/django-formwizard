from django.test import TestCase
from django import http
from django import forms
from formwizard.forms import FormWizard, SessionFormWizard, CookieFormWizard
from django.conf import settings
from django.utils.importlib import import_module
from django.contrib.auth.models import User

class DummyRequest(http.HttpRequest):
    def __init__(self, POST=None):
        super(DummyRequest, self).__init__()
        self.method = POST and "POST" or "GET"
        if POST is not None:
            self.POST.update(POST)
        self.session = {}
        self._dont_enforce_csrf_checks = True

def get_request(*args, **kwargs):
    request = DummyRequest(*args, **kwargs)
    engine = import_module(settings.SESSION_ENGINE)
    request.session = engine.SessionStore(None)
    return request

class Step1(forms.Form):
    name = forms.CharField()

class Step2(forms.Form):
    name = forms.CharField()

class Step3(forms.Form):
    data = forms.CharField()

class UserForm(forms.ModelForm):
    class Meta:
        model = User

UserFormSet = forms.models.modelformset_factory(User, form=UserForm, extra=2)

class TestWizard(FormWizard):
    pass

class FormTests(TestCase):
    def test_form_init(self):
        testform = TestWizard.build_init_kwargs(
            'formwizard.storage.session.SessionStorage', [Step1, Step2])
        self.assertEquals(testform['form_list'], {u'0': Step1, u'1': Step2})

        testform = TestWizard.build_init_kwargs(
            'formwizard.storage.session.SessionStorage',
            [('start', Step1), ('step2', Step2)])
        self.assertEquals(
            testform['form_list'], {u'start': Step1, u'step2': Step2})

        testform = TestWizard.build_init_kwargs(
            'formwizard.storage.session.SessionStorage',
            [Step1, Step2, ('finish', Step3)])
        self.assertEquals(
            testform['form_list'], {u'0': Step1, u'1': Step2, u'finish': Step3})

    def test_first_step(self):
        request = get_request()

        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage', [Step1, Step2])
        response, instance = testform(request, testmode=True)
        self.assertEquals(instance.determine_step(), u'0')

        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', Step1), ('step2', Step2)])
        response, instance = testform(request, testmode=True)

        self.assertEquals(instance.determine_step(), 'start')

    def test_persistence(self):
        request = get_request({'name': 'data1'})

        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', Step1), ('step2', Step2)])
        response, instance = testform(request, testmode=True)
        self.assertEquals(instance.determine_step(), 'start')
        instance.storage.set_current_step('step2')

        testform2 = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', Step1), ('step2', Step2)])
        response, instance = testform2(request, testmode=True)
        self.assertEquals(instance.determine_step(), 'step2')

    def test_form_condition(self):
        request = get_request()

        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', Step1), ('step2', Step2), ('step3', Step3)],
            condition_list={'step2': True})
        response, instance = testform(request, testmode=True)
        self.assertEquals(instance.get_next_step(), 'step2')

        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', Step1), ('step2', Step2), ('step3', Step3)],
            condition_list={'step2': False})
        response, instance = testform(request, testmode=True)
        self.assertEquals(instance.get_next_step(), 'step3')

    def test_add_extra_context(self):
        request = get_request()

        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', Step1), ('step2', Step2)])

        response, instance = testform(
            request, extra_context={'key1': 'value1'}, testmode=True)
        self.assertEqual(instance.get_extra_context(), {'key1': 'value1'})

        request.method = 'POST'
        response, instance = testform(
            request, extra_context={'key1': 'value1'}, testmode=True)
        self.assertEqual(instance.get_extra_context(), {'key1': 'value1'})

    def test_form_prefix(self):
        request = get_request()

        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', Step1), ('step2', Step2)])
        response, instance = testform(request, testmode=True)

        self.assertEqual(instance.get_form_prefix(), 'start')
        self.assertEqual(instance.get_form_prefix('another'), 'another')

    def test_form_initial(self):
        request = get_request()

        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', Step1), ('step2', Step2)],
            initial_list={'start': {'name': 'value1'}})
        response, instance = testform(request, testmode=True)

        self.assertEqual(instance.get_form_initial('start'), {'name': 'value1'})
        self.assertEqual(instance.get_form_initial('step2'), {})

    def test_form_instance(self):
        request = get_request()
        the_instance = User()
        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', UserForm), ('step2', Step2)],
            instance_list={'start': the_instance})
        response, instance = testform(request, testmode=True)

        self.assertEqual(
            instance.get_form_instance('start'),
            the_instance)
        self.assertEqual(
            instance.get_form_instance('non_exist_instance'),
            None)

    def test_formset_instance(self):
        request = get_request()
        the_instance1, created = User.objects.get_or_create(
            username='testuser1')
        the_instance2, created = User.objects.get_or_create(
            username='testuser2')
        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', UserFormSet), ('step2', Step2)],
            instance_list={'start': User.objects.filter(username='testuser1')})
        response, instance = testform(request, testmode=True)

        self.assertEqual(list(instance.get_form_instance('start')), [the_instance1])
        self.assertEqual(instance.get_form_instance('non_exist_instance'), None)

        self.assertEqual(instance.get_form().initial_form_count(), 1)

    def test_done(self):
        request = get_request()

        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', Step1), ('step2', Step2)])
        response, instance = testform(request, testmode=True)

        self.assertRaises(NotImplementedError, instance.done, None)

    def test_revalidation(self):
        request = get_request()

        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', Step1), ('step2', Step2)])
        response, instance = testform(request, testmode=True)
        instance.render_done(None)
        self.assertEqual(instance.storage.get_current_step(), 'start')

    def test_form_refresh(self):
        testform = TestWizard.as_view(
            'formwizard.storage.session.SessionStorage',
            [('start', Step1), ('step2', UserFormSet)])

        request = get_request({'start-name': 'foo'})
        request.method = 'POST'

        response, instance = testform(request, testmode=True)
        self.assertEqual(instance.storage.get_current_step(), 'step2')
        # refresh form
        response, instance = testform(request, testmode=True)
        self.assertEqual(instance.storage.get_current_step(), 'step2')

class SessionFormTests(TestCase):
    def test_init(self):
        request = get_request()
        testform = SessionFormWizard.as_view([('start', Step1)])

        self.assertEqual(type(testform(request)), http.HttpResponse)

class CookieFormTests(TestCase):
    def test_init(self):
        request = get_request()
        testform = CookieFormWizard.as_view([('start', Step1)])

        self.assertEqual(type(testform(request)), http.HttpResponse)

