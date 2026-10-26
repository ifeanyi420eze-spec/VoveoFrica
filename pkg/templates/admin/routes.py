from functools import wraps

from flask import Blueprint, abort, render_template, session

from pkg.models import Match, Report, User


admin_routes = Blueprint("admin", __name__, url_prefix="/admin")


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
    return render_template(
        "admin/pages/user_management.html",
        users=User.query.order_by(User.created_at.desc()).all(),
    )


@admin_routes.route("/matches")
@admin_required
def matches():
    return render_template(
        "admin/pages/match_management.html",
        matches=Match.query.order_by(Match.created_at.desc()).all(),
    )


@admin_routes.route("/reports")
@admin_required
def reports():
    return render_template(
        "admin/pages/reports_management.html",
        reports=Report.query.order_by(Report.created_at.desc()).all(),
    )