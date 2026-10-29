from functools import wraps

from datetime import datetime

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from pkg import db
from pkg.models import Match, Notification, Report, User


admin_routes = Blueprint("admin", __name__, url_prefix="/admin")
ADMIN_PAGE_SIZE = 50


def _admin_page():
    try:
        return max(1, int(request.args.get("page", "1")))
    except ValueError:
        return 1


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("is_admin"):
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


@admin_routes.route("/")
@admin_required
def dashboard():
    return render_template(
        "admin/pages/admin_dashboard.html",
        user_count=User.query.count(),
        match_count=Match.query.count(),
        report_count=Report.query.count(),
    )


@admin_routes.route("/users")
@admin_required
def users():
    pagination = db.paginate(
        User.query.order_by(User.created_at.desc()),
        page=_admin_page(),
        per_page=ADMIN_PAGE_SIZE,
        error_out=False,
    )
    return render_template(
        "admin/pages/user_management.html",
        users=pagination.items,
        pagination=pagination,
    )


@admin_routes.route("/users/<int:user_id>/verification", methods=["POST"])
@admin_required
def review_verification(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    decision = request.form.get("decision")
    if decision not in {"verified", "rejected"} or user.verification_status != "pending":
        abort(400, "A pending verification request and valid decision are required.")
    user.verification_status = decision
    user.verification_reviewed_at = datetime.utcnow()
    status_text = "approved" if decision == "verified" else "not approved"
    db.session.add(
        Notification(
            user_id=user.id,
            text=f"Your profile verification request was {status_text}.",
            category="verification",
            link_url=url_for("user.verification"),
        )
    )
    db.session.commit()
    return redirect(url_for("admin.users"))


@admin_routes.route("/matches")
@admin_required
def matches():
    pagination = db.paginate(
        Match.query.order_by(Match.created_at.desc()),
        page=_admin_page(),
        per_page=ADMIN_PAGE_SIZE,
        error_out=False,
    )
    return render_template(
        "admin/pages/match_management.html",
        matches=pagination.items,
        pagination=pagination,
    )


@admin_routes.route("/reports")
@admin_required
def reports():
    pagination = db.paginate(
        Report.query.order_by(Report.created_at.desc()),
        page=_admin_page(),
        per_page=ADMIN_PAGE_SIZE,
        error_out=False,
    )
    return render_template(
        "admin/pages/reports_management.html",
        reports=pagination.items,
        pagination=pagination,
    )