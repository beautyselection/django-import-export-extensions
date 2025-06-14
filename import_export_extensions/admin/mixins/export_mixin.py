import typing

from django.core.exceptions import PermissionDenied
from django.core.handlers.wsgi import WSGIRequest
from django.http import (
    HttpResponse,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import re_path, reverse
from django.utils.translation import gettext_lazy as _

from import_export import admin as import_export_admin
from import_export import mixins as import_export_mixins
from import_export.forms import ExportForm

from ... import models
from . import base_mixin, types


class CeleryExportAdminMixin(
    import_export_mixins.BaseExportMixin,
    base_mixin.BaseCeleryImportExportAdminMixin,
):
    """Admin mixin for celery export.

    Admin export work-flow is:
        GET `celery_export_action()` - display form with format type input

        POST `celery_export_action()` - create ExportJob and starts data export
            This view redirects to next view:

        GET `celery_export_job_status_view()` - display ExportJob status (with
            progress bar). When data exporting is done, redirect to next view:

        GET `celery_export_job_results_view()` - display export results. If no
            errors - success message and link to the file with exported data.
            If errors - traceback and error message.

    """

    # export data encoding
    to_encoding = "utf-8"

    export_form_class: type[ExportForm] = ExportForm

    # template used to display ExportForm
    celery_export_template_name = "admin/import_export/export.html"

    export_status_template_name = (
        "admin/import_export_extensions/celery_export_status.html"
    )

    export_results_template_name = (
        "admin/import_export_extensions/celery_export_results.html"
    )

    import_export_change_list_template = (
        "admin/import_export/change_list_export.html"
    )

    # Statuses that should be displayed on 'results' page
    export_results_statuses = models.ExportJob.export_finished_statuses

    # Copy methods of mixin from original package to reuse it here
    has_export_permission = (
        import_export_admin.ExportMixin.has_export_permission
    )
    get_export_form_class = import_export_admin.ExportMixin.get_export_form_class  # noqa

    def get_export_context_data(self, **kwargs):
        """Get context data for export."""
        return self.get_context_data(**kwargs)

    def get_urls(self):
        """Return list of urls.

        /<model/celery-export/:
            ExportForm ('export_action' method)
        /<model>/celery-export/<ID>/:
            status of ExportJob and progress bar ('export_job_status_view')
        /<model>/celery-export/<ID>/results/:
            table with export results (errors)

        """
        urls = super().get_urls()
        export_urls = [
            re_path(
                r"^celery-export/$",
                self.admin_site.admin_view(self.celery_export_action),
                name=f"{self.model_info.app_model_name}_export",
            ),
            re_path(
                r"^celery-export/(?P<job_id>\d+)/$",
                self.admin_site.admin_view(self.export_job_status_view),
                name=(
                    f"{self.model_info.app_model_name}"
                    f"_export_job_status"
                ),
            ),
            re_path(
                r"^celery-export/(?P<job_id>\d+)/results/$",
                self.admin_site.admin_view(
                    self.export_job_results_view,
                ),
                name=(
                    f"{self.model_info.app_model_name}"
                    f"_export_job_results"
                ),
            ),
        ]
        return export_urls + urls

    def celery_export_action(self, request, *args, **kwargs):
        """Show and handle export.

        GET: show export form with format_type input
        POST: create ExportJob instance and redirect to it's status

        """
        if not self.has_export_permission(request):
            raise PermissionDenied

        formats = self.get_export_formats()
        form_type = self.get_export_form_class()
        form = form_type(
            formats=formats,
            resources=self.get_export_resource_classes(request),
            data=request.POST or None,
        )
        resource_kwargs = self.get_export_resource_kwargs(
            *args,
            **kwargs,
            request=request,
        )
        if request.method == "POST" and form.is_valid():
            file_format = formats[int(form.cleaned_data["format"])]
            # create ExportJob and redirect to page with it's status
            job = self.create_export_job(
                request=request,
                resource_class=self.choose_export_resource_class(
                    form,
                    request,
                ),
                resource_kwargs=resource_kwargs,
                file_format=file_format,
            )
            return self._redirect_to_export_status_page(
                request=request,
                job=job,
            )

        # GET: display Export Form
        context = self.get_export_context_data()
        context.update(self.admin_site.each_context(request))

        context["title"] = _("Export")
        context["form"] = form
        context["opts"] = self.model_info.meta
        request.current_app = self.admin_site.name

        return TemplateResponse(
            request=request,
            template=[self.celery_export_template_name],
            context=context,
        )

    def export_job_status_view(
        self,
        request: WSGIRequest,
        job_id: int,
        **kwargs,
    ) -> HttpResponse:
        """View to track export job status.

        Displays current export job status and progress (using JS + another
        view).

        If job result is ready - redirects to another page to see results.

        """
        if not self.has_export_permission(request):
            raise PermissionDenied

        job = self.get_export_job(request=request, job_id=job_id)
        if job.export_status in self.export_results_statuses:
            return self._redirect_to_export_results_page(
                request=request,
                job=job,
            )

        context = self.get_export_context_data()
        job_url = reverse("admin:export_job_progress", args=(job.id,))

        context["title"] = _("Export status")
        context["opts"] = self.model_info.meta
        context["export_job"] = job
        context["export_job_url"] = job_url
        request.current_app = self.admin_site.name
        return TemplateResponse(
            request=request,
            template=[self.export_status_template_name],
            context=context,
        )

    def export_job_results_view(
        self,
        request: WSGIRequest,
        job_id: int,
        *args,
        **kwargs,
    ) -> HttpResponse:
        """Display export results.

        GET-request:
            * show message
            * if no errors - show file link
            * if errors - show traceback and error

        """
        if not self.has_export_permission(request):
            raise PermissionDenied

        job = self.get_export_job(request=request, job_id=job_id)
        if job.export_status not in self.export_results_statuses:
            return self._redirect_to_export_status_page(
                request=request,
                job=job,
            )

        context = self.get_export_context_data()

        # GET request, show export results
        context["title"] = _("Export results")
        context["opts"] = self.model._meta
        context["export_job"] = job
        context["result"] = job.export_status

        return TemplateResponse(
            request=request,
            template=[self.export_results_template_name],
            context=context,
        )

    def create_export_job(
        self,
        request: WSGIRequest,
        resource_class: types.ResourceType,
        resource_kwargs: dict[str, typing.Any],
        file_format: types.FormatType,
    ) -> models.ExportJob:
        """Create and return instance of export job with chosen format."""
        job = models.ExportJob.objects.create(
            resource_path=resource_class.class_path,
            resource_kwargs=resource_kwargs,
            file_format_path=(
                f"{file_format.__module__}.{file_format.__name__}"
            ),
        )
        return job

    def get_export_job(
        self,
        request: WSGIRequest,
        job_id: int,
    ) -> models.ExportJob:
        """Get ExportJob instance.

        Raises
            Http404

        """
        return get_object_or_404(models.ExportJob, id=job_id)

    def get_resource_kwargs(self, request, *args, **kwargs):
        """Return filter kwargs for resource queryset."""
        resource_kwargs = super().get_resource_kwargs(request, *args, **kwargs)
        resource_kwargs["admin_filters"] = self._export_get_admin_filter(
            request=request,
        )
        return resource_kwargs

    def _export_get_admin_filter(
        self,
        request: WSGIRequest,
    ) -> dict[str, typing.Any]:
        """Get GET query params to pass them to resource class."""
        query_params = dict(request.GET)
        search_kwargs = self._export_get_search_filter(
            request=request,
            value=query_params.pop("q", []),
        )
        admin_filter = {}
        admin_filter = {
            key: value
            for key in query_params
            for value in query_params[key]
            if key in self.get_list_filter(request)
        }
        admin_filter["search"] = search_kwargs
        return admin_filter


    def _export_get_search_filter(
        self,
        request: WSGIRequest,
        value: list[str],
    ) -> dict[str, str]:
        """Return search filter for resource class.

        Inspired by https://github.com/django/django/blob/d6925f0d6beb3c08ae24bdb8fd83ddb13d1756e4/django/contrib/admin/options.py#L1130

        """
        extracted_value: str = (
            value[0]
            if value
            else ""
        )
        search_kwargs = {}
        used_fields = []
        for search_field in self.get_search_fields(request):
            lookup_field, model_field = self._export_construct_search(
                search_field,
            )
            if model_field in used_fields:
                continue
            used_fields.append(model_field)
            search_kwargs[lookup_field] = extracted_value
        return search_kwargs

    def _export_construct_search(
        self,
        field_name: str,
    ) -> tuple[str, str]:
        """Get search lookups.

        Inspired by https://github.com/django/django/blob/d6925f0d6beb3c08ae24bdb8fd83ddb13d1756e4/django/contrib/admin/options.py#L1137

        """
        match (search_type := field_name[0]):
            case "^":
                lookup = "istartswith"
            case "=":
                lookup = "iexact"
            case "@":
                lookup = "search"
            case _:
                search_type = ""
                lookup = "icontains"
        field_name = field_name.removeprefix(search_type)
        return f"{field_name}__{lookup}", field_name

    def _redirect_to_export_status_page(
        self,
        request: WSGIRequest,
        job: models.ExportJob,
    ) -> HttpResponse:
        """Shortcut for redirecting to job's status page."""
        url_name = (
            f"{self.admin_site.name}:{self.model_info.app_model_name}_export_job_status"
        )
        url = reverse(url_name, kwargs=dict(job_id=job.id))
        query = request.GET.urlencode()
        url = f"{url}?{query}" if query else url
        return HttpResponseRedirect(redirect_to=url)

    def _redirect_to_export_results_page(
        self,
        request: WSGIRequest,
        job: models.ExportJob,
    ) -> HttpResponse:
        """Shortcut for redirecting to job's results page."""
        url_name = (
            f"{self.admin_site.name}:{self.model_info.app_model_name}_export_job_results"
        )
        url = reverse(url_name, kwargs=dict(job_id=job.id))
        query = request.GET.urlencode()
        url = f"{url}?{query}" if query else url
        return HttpResponseRedirect(redirect_to=url)

    def changelist_view(
        self,
        request: WSGIRequest,
        context: dict[str, typing.Any] | None = None,
    ):
        """Add the check for permission to changelist template context."""
        context = context or {}
        context["has_export_permission"] = self.has_export_permission(request)
        return super().changelist_view(request, context)
