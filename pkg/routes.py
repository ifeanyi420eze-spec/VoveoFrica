"""Public-page routes for the VOVEOFRICA website."""

from flask import Blueprint, redirect, render_template, url_for

from pkg.models import Match, SubscriptionPlan, User


# Public templates live in the voveo_pages directory under Flask's template root.
root_routes = Blueprint("root", __name__)


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
    return render_template("voveo_pages/subscription.html", plans=plans)


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
