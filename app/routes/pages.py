"""Public-page routes for the VOVEOFRICA website."""

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    send_from_directory,
    session,
    url_for,
)

from app.models import Match, SubscriptionPlan, User
from app.services.payments import paystack_configuration_is_ready


# Public templates live in the voveo_pages directory under Flask's template root.
root_routes = Blueprint("root", __name__)


@root_routes.route("/favicon.ico")
def favicon():
    """Serve the existing brand image for browsers requesting a favicon."""
    return send_from_directory(
        current_app.static_folder,
        "images/logo.png",
        mimetype="image/png",
    )


@root_routes.route("/")
def home():
    """Render the public landing page."""
    return render_template(
        "voveo_pages/index.html",
        member_count=User.query.count(),
        match_count=Match.query.count(),
    )


@root_routes.route("/about")
def about():
    """Render the public about page."""
    return render_template("voveo_pages/about_us.html")


@root_routes.route("/contact")
def contact():
    """Render the public contact page."""
    return render_template("voveo_pages/contact_us.html")


@root_routes.route("/subscription")
def subscription():
    """Render the available subscription plans."""
    plans = SubscriptionPlan.query.filter_by(is_active=True).order_by(
        SubscriptionPlan.duration_days
    ).all()
    premium_plans = [plan for plan in plans if plan.plan_type == "premium"]
    boost_plans = [plan for plan in plans if plan.plan_type == "boost"]
    monthly_equivalents = {}
    monthly_plan = next(
        (plan for plan in premium_plans if plan.name.casefold() == "monthly"),
        None,
    )
    for plan in premium_plans:
        months = (
            max(1, round(plan.duration_days / monthly_plan.duration_days))
            if monthly_plan and monthly_plan.duration_days > 0
            else 0
        )
        if months:
            baseline = monthly_plan.amount_ngn * months
            monthly_equivalents[plan.id] = {
                "amount": plan.amount_ngn / months,
                "months": months,
                "savings_percent": max(
                    0,
                    round((1 - plan.amount_ngn / baseline) * 100)
                    if baseline
                    else 0,
                ),
            }
    return render_template(
        "voveo_pages/subscription.html",
        plans=premium_plans,
        boost_plans=boost_plans,
        monthly_equivalents=monthly_equivalents,
        logged_in=bool(session.get("user_id")),
        checkout_available=paystack_configuration_is_ready(current_app.config),
    )


@root_routes.route("/support")
def support():
    """Render the support alias for the customer-care page."""
    return render_template("voveo_pages/support.html")


@root_routes.route("/terms")
def terms():
    """Render the terms page."""
    return render_template("voveo_pages/terms.html")


@root_routes.route("/services")
def services():
    """Keep the old services URL working by redirecting to subscription plans."""
    return redirect(url_for("root.subscription"))


@root_routes.route("/faq")
def faq():
    """Keep the old FAQ URL working through the customer-care FAQ section."""
    return redirect(url_for("root.support"))


@root_routes.route("/help")
def help_page():
    """Keep the old help URL working by redirecting to customer care."""
    return redirect(url_for("root.support"))


@root_routes.route("/customer-care")
def customer_care():
    """Provide a readable URL alias for the customer-care page."""
    return redirect(url_for("root.support"))


@root_routes.route("/feedback")
def feedback():
    """Send feedback-page visitors to the available contact page."""
    return redirect(url_for("root.contact"))


@root_routes.route("/terms-of-service")
def terms_of_service():
    """Keep the legacy terms URL working by redirecting to the canonical terms page."""
    return redirect(url_for("root.terms"))


@root_routes.route("/blog")
def blog():
    """Render the public blog landing page."""
    return render_template("voveo_pages/blog.html")


@root_routes.route("/privacy")
def privacy():
    """Render the privacy notice."""
    return render_template("voveo_pages/privacy_policy.html")


@root_routes.route("/privacy-policy")
def privacy_policy():
    """Render the privacy notice at its canonical URL."""
    return render_template("voveo_pages/privacy_policy.html")


@root_routes.route("/cookie-policy")
def cookie_policy():
    """Render information about cookies and browser storage."""
    return render_template("voveo_pages/cookie_policy.html")


@root_routes.route("/accessibility")
def accessibility():
    """Render the accessibility statement."""
    return render_template("voveo_pages/accessibility.html")
