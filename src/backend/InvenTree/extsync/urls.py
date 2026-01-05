"""URL configuration for extsync endpoints."""

from django.urls import path

from .views import ExternalDocumentCreateView, ExternalDocumentPdfView, ExternalOrderView, JobStatusView

urlpatterns = [
    path('orders/<str:order_id>/', ExternalOrderView.as_view(), name='ext-order'),
    path('orders/<str:order_id>/documents/', ExternalDocumentCreateView.as_view(), name='ext-order-documents'),
    path('documents/<uuid:document_id>/pdf/', ExternalDocumentPdfView.as_view(), name='ext-document-pdf'),
    path('jobs/<uuid:job_id>/', JobStatusView.as_view(), name='ext-job-status'),
]
