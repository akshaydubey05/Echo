from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.template.loader import render_to_string
from .fields import OrderField


class Subject(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title


class Course(models.Model):
    owner = models.ForeignKey(User,
                              related_name='courses_created',
                              on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject,
                                related_name='courses',
                                on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    overview = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    students = models.ManyToManyField(User,
                                      related_name='courses_joined',
                                      blank=True)

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=['subject'], name='course_subject_idx'),
            models.Index(fields=['owner'], name='course_owner_idx'),
            models.Index(fields=['created'], name='course_created_idx'),
        ]

    def __str__(self):
        return self.title


class Module(models.Model):
    course = models.ForeignKey(Course,
                               related_name='modules',
                               on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = OrderField(blank=True, for_fields=['course'])

    class Meta:
        ordering = ['order']
        indexes = [
            models.Index(fields=['course'], name='module_course_idx'),
            models.Index(fields=['order'], name='module_order_idx'),
        ]

    def __str__(self):
        return f'{self.order}. {self.title}'


class Content(models.Model):
    module = models.ForeignKey(Module,
                               related_name='contents',
                               on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType,
                                     on_delete=models.CASCADE,
                                     limit_choices_to={'model__in':(
                                     'text',
                                     'video',
                                     'image',
                                     'file')})
    object_id = models.PositiveIntegerField()
    item = GenericForeignKey('content_type', 'object_id')
    order = OrderField(blank=True, for_fields=['module'])

    class Meta:
        ordering = ['order']
        indexes = [
            models.Index(fields=['module'], name='content_module_idx'),
            models.Index(fields=['content_type', 'object_id'], name='content_gfk_idx'),
            models.Index(fields=['order'], name='content_order_idx'),
        ]


class ItemBase(models.Model):
    owner = models.ForeignKey(User,
                              related_name='%(class)s_related',
                              on_delete=models.CASCADE)
    title = models.CharField(max_length=250)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.title

    def render(self):
        return render_to_string(
            f'courses/content/{self._meta.model_name}.html',
            {'item': self})


class Text(ItemBase):
    content = models.TextField()


class File(ItemBase):
    file = models.FileField(upload_to='files')


class Image(ItemBase):
       file = models.FileField(upload_to='images')


class Video(ItemBase):
    url = models.URLField()


class StudentProgress(models.Model):
    student = models.ForeignKey(User,
                                related_name='progress',
                                on_delete=models.CASCADE)
    course = models.ForeignKey(Course,
                               related_name='progress_by_students',
                               on_delete=models.CASCADE)
    content = models.ForeignKey(Content,
                                related_name='completed_by_students',
                                on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('student', 'content')
        ordering = ['-completed_at']
        indexes = [
            models.Index(fields=['student', 'course'], name='student_course_progress_idx'),
            models.Index(fields=['student', 'content'], name='student_content_completed_idx'), # Supports unique_together and lookups
        ]

    def __str__(self):
        return f"{self.student} completed {self.content} in {self.course} at {self.completed_at}"
