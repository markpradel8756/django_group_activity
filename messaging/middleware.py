import logging

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.shortcuts import render

logger = logging.getLogger(__name__)


class SafeViewErrors:
    """Return a generic page for unexpected view errors, including in local demos."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, (Http404, PermissionDenied, SuspiciousOperation)):
            return None
        logger.error("Unhandled workspace error (%s)", type(exception).__name__)
        return render(request, "500.html", status=500)
