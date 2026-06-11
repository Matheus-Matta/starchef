from django.template.loader import render_to_string

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.printers.models import PrintJob


def render_print_html(order, job_type):
    template = "printers/kitchen_ticket.html" if "ticket" in job_type else "printers/receipt.html"
    return render_to_string(template, {"order": order, "items": order.items.select_related("product").all()})


def register_print_job(*, order, user, job_type=PrintJob.TYPE_RECEIPT, printer=None):
    with tenant_context(order.account):
        if printer and printer.account_id != order.account_id:
            raise ValueError("Printer does not belong to the order account.")

        html = render_print_html(order, job_type)
        job = PrintJob.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            printer=printer,
            order=order,
            job_type=job_type,
            status=PrintJob.STATUS_RENDERED,
            payload={"account_id": str(order.account_id), "order_id": str(order.id), "sequence": order.sequence},
            html_content=html,
            printed_by=user,
            created_by=user,
            updated_by=user,
        )
        record_audit(action=AuditLog.ACTION_PRINTED, instance=job, actor=user, metadata={"job_type": job_type})
        return job
