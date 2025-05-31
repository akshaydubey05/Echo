from django.shortcuts import redirect, get_object_or_404
from django.views.generic.base import TemplateResponseMixin, View
from django.views.generic.list import ListView
from django.views.generic.edit import CreateView, UpdateView, \
                                      DeleteView
from django.views.generic.detail import DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, \
                                       PermissionRequiredMixin
from django.urls import reverse_lazy
from django.forms.models import modelform_factory
from django.apps import apps
from django.db.models import Count, Q
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from braces.views import CsrfExemptMixin, JsonRequestResponseMixin
from students.forms import CourseEnrollForm
from .forms import ModuleFormSet
from .models import Course, Module, Content, Subject, StudentProgress


class ManageCourseListView(ListView):
    model = Course
    template_name = 'courses/manage/course/list.html'

    def get_queryset(self):
        qs = super().get_queryset().select_related('owner', 'subject')
        return qs.filter(owner=self.request.user)


class OwnerMixin:
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(owner=self.request.user)


class OwnerEditMixin:
    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class OwnerCourseMixin(OwnerMixin,
                       LoginRequiredMixin,
                       PermissionRequiredMixin):
    model = Course
    fields = ['subject', 'title', 'slug', 'overview']
    success_url = reverse_lazy('manage_course_list')


class OwnerCourseEditMixin(OwnerCourseMixin, OwnerEditMixin):
    template_name = 'courses/manage/course/form.html'


class ManageCourseListView(OwnerCourseMixin, ListView):
    template_name = 'courses/manage/course/list.html'
    permission_required = 'courses.view_course'


class CourseCreateView(OwnerCourseEditMixin, CreateView):
    permission_required = 'courses.add_course'

    def form_valid(self, form):
        response = super().form_valid(form)
        cache.delete('all_courses')
        if self.object.subject: # Ensure subject exists
            cache.delete(f'subject_{self.object.subject.id}_courses')
        cache.delete('all_subjects')
        return response


class CourseUpdateView(OwnerCourseEditMixin, UpdateView):
    permission_required = 'courses.change_course'

    def form_valid(self, form):
        old_subject_id = None
        if self.object and self.object.subject: # Check if object and its subject exist
            old_subject_id = self.object.subject.id

        response = super().form_valid(form)

        new_subject_id = None
        if self.object and self.object.subject: # Check for new subject
            new_subject_id = self.object.subject.id

        cache.delete('all_courses')
        if new_subject_id:
            cache.delete(f'subject_{new_subject_id}_courses')

        if old_subject_id and old_subject_id != new_subject_id:
            cache.delete(f'subject_{old_subject_id}_courses')
        cache.delete('all_subjects')
        return response


class CourseDeleteView(OwnerCourseMixin, DeleteView):
    template_name = 'courses/manage/course/delete.html'
    permission_required = 'courses.delete_course'

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        subject_id = None
        if obj.subject: # Ensure subject exists
            subject_id = obj.subject.id

        response = super().delete(request, *args, **kwargs)

        cache.delete('all_courses')
        if subject_id:
            cache.delete(f'subject_{subject_id}_courses')
        cache.delete('all_subjects')
        return response


class CourseModuleUpdateView(TemplateResponseMixin, View):
    template_name = 'courses/manage/module/formset.html'
    course = None

    def get_formset(self, data=None):
        return ModuleFormSet(instance=self.course,
                             data=data)

    def dispatch(self, request, pk):
        self.course = get_object_or_404(Course,
                                        id=pk,
                                        owner=request.user)
        return super().dispatch(request, pk)

    def get(self, request, *args, **kwargs):
        formset = self.get_formset()
        return self.render_to_response({'course': self.course,
                                        'formset': formset})

    def post(self, request, *args, **kwargs):
        formset = self.get_formset(data=request.POST)
        if formset.is_valid():
            formset.save()
            return redirect('manage_course_list')
        return self.render_to_response({'course': self.course,
                                        'formset': formset})


class ContentCreateUpdateView(TemplateResponseMixin, View):
    module = None
    model = None
    obj = None
    template_name = 'courses/manage/content/form.html'

    def get_model(self, model_name):
        if model_name in ['text', 'video', 'image', 'file']:
            return apps.get_model(app_label='courses',
                                  model_name=model_name)
        return None

    def get_form(self, model, *args, **kwargs):
        Form = modelform_factory(model, exclude=['owner',
                                                 'order',
                                                 'created',
                                                 'updated'])
        return Form(*args, **kwargs)

    def dispatch(self, request, module_id, model_name, id=None):
        self.module = get_object_or_404(Module,
                                       id=module_id,
                                       course__owner=request.user)
        self.model = self.get_model(model_name)
        if id:
            self.obj = get_object_or_404(self.model,
                                         id=id,
                                         owner=request.user)
        return super().dispatch(request, module_id, model_name, id)

    def get(self, request, module_id, model_name, id=None):
        form = self.get_form(self.model, instance=self.obj)
        return self.render_to_response({'form': form,
                                        'object': self.obj})

    def post(self, request, module_id, model_name, id=None):
        form = self.get_form(self.model,
                             instance=self.obj,
                             data=request.POST,
                             files=request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.owner = request.user
            obj.save()
            if not id:
                # new content
                Content.objects.create(module=self.module,
                                       item=obj)
            return redirect('module_content_list', self.module.id)
        return self.render_to_response({'form': form,
                                        'object': self.obj})


class ContentDeleteView(View):
    def post(self, request, id):
        content = get_object_or_404(Content,
                               id=id,
                               module__course__owner=request.user)
        module = content.module
        content.item.delete()
        content.delete()
        return redirect('module_content_list', module.id)


class ModuleContentListView(TemplateResponseMixin, View):
    template_name = 'courses/manage/module/content_list.html'

    def get(self, request, module_id):
        module = get_object_or_404(Module,
                                   id=module_id,
                                   course__owner=request.user)
        # Get contents for the module and prefetch the 'item' for each content
        module_contents = module.contents.prefetch_related('item')
        return self.render_to_response({'module': module,
                                        'module_contents': module_contents})


class ModuleOrderView(CsrfExemptMixin,
                      JsonRequestResponseMixin,
                      View):
    def post(self, request):
        for id, order in self.request_json.items():
            Module.objects.filter(id=id,
                   course__owner=request.user).update(order=order)
        return self.render_json_response({'saved': 'OK'})


class ContentOrderView(CsrfExemptMixin,
                       JsonRequestResponseMixin,
                       View):
    def post(self, request):
        for id, order in self.request_json.items():
            Content.objects.filter(id=id,
                       module__course__owner=request.user) \
                       .update(order=order)
        return self.render_json_response({'saved': 'OK'})


class CourseListView(TemplateResponseMixin, View):
    model = Course
    template_name = 'courses/course/list.html'
    def get(self, request, subject=None):
        subjects = cache.get('all_subjects')
        if not subjects:
            subjects = Subject.objects.annotate(
                            total_courses=Count('courses'))
            cache.set('all_subjects', subjects)

        all_courses_base = Course.objects.select_related('subject').annotate(
                        total_modules=Count('modules'))

        search_query = request.GET.get('q', '')
        can_use_cache_for_courses = not search_query # If searching, don't use cached course lists

        if search_query:
            all_courses_base = all_courses_base.filter(
                Q(title__icontains=search_query) | Q(overview__icontains=search_query)
            )

        if subject:
            subject = get_object_or_404(Subject, slug=subject)
            key = f'subject_{subject.id}_courses'
            courses = None
            if can_use_cache_for_courses:
                courses = cache.get(key)

            if not courses:
                courses = all_courses_base.filter(subject=subject) # Already has select_related('subject')
                if can_use_cache_for_courses: # Only cache if not a search result
                    cache.set(key, courses)
        else:
            key = 'all_courses'
            courses = None
            if can_use_cache_for_courses:
                courses = cache.get(key)

            if not courses:
                courses = all_courses_base
                if can_use_cache_for_courses: # Only cache if not a search result
                    cache.set(key, courses)

        return self.render_to_response({'subjects': subjects,
                                        'subject': subject,
                                        'courses': courses,
                                        'search_query': search_query})


class CourseDetailView(DetailView):
    model = Course
    template_name = 'courses/course/detail.html'

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.prefetch_related(
            'modules__contents__item', # For displaying content titles efficiently
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['enroll_form'] = CourseEnrollForm(initial={'course': self.object})

        completed_content_ids = set()
        if self.request.user.is_authenticated:
            progress_entries = StudentProgress.objects.filter(
                student=self.request.user,
                course=self.object,
                is_completed=True
            ).values_list('content_id', flat=True)
            completed_content_ids.update(progress_entries)

        context['completed_content_ids'] = completed_content_ids
        return context


class MarkContentCompleteView(LoginRequiredMixin, View):
    def post(self, request, content_id):
        content = get_object_or_404(Content, id=content_id)
        course = content.module.course

        progress, created = StudentProgress.objects.get_or_create(
            student=request.user,
            content=content,
            defaults={'course': course}
        )

        # Toggle completion status
        progress.is_completed = not progress.is_completed
        if progress.is_completed:
            progress.completed_at = timezone.now()
        # If it becomes False, completed_at retains its last value or could be set to None
        # Based on subtask: "if is_completed becomes true, completed_at should be updated"
        # This implies no change to completed_at if it becomes false.

        progress.save()
        return redirect(reverse('course_detail', args=[course.slug]))
