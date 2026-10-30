import logging
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from db_manager.services import (
    create_database,
    drop_database,
    is_port_in_use,
    list_databases,
    verify_master_password,
)

logger = logging.getLogger(__name__)


def is_authenticated_db_manager(request) -> bool:
    """Helper to check if the current session is authenticated for Database Manager."""
    return bool(request.session.get("db_manager_authenticated"))


def db_manager_index_view(request):
    """
    Main entry point for Odoo-style Database Manager.
    If not authenticated with Master Password, shows password prompt.
    Otherwise displays database dashboard.
    """
    if not is_authenticated_db_manager(request):
        return render(request, "db_manager/auth.html")

    try:
        databases = list_databases()
    except Exception as e:
        logger.error("Failed to list databases: %s", str(e))
        messages.error(request, f"Unable to connect to PostgreSQL server: {str(e)}")
        databases = []

    # Check port status for quick launch references
    port_8000_active = is_port_in_use(8000)
    port_8001_active = is_port_in_use(8001)

    context = {
        "databases": databases,
        "port_8000_active": port_8000_active,
        "port_8001_active": port_8001_active,
    }
    return render(request, "db_manager/dashboard.html", context)


@require_http_methods(["POST"])
def db_manager_auth_view(request):
    """Authenticates the session using the Master Password."""
    master_password = request.POST.get("master_password", "").strip()
    if verify_master_password(master_password):
        request.session["db_manager_authenticated"] = True
        messages.success(request, "Authenticated to Database Manager.")
        return redirect("db_manager_index")
    else:
        messages.error(request, "Invalid Master Password.")
        return render(request, "db_manager/auth.html")


@require_http_methods(["GET", "POST"])
def db_manager_logout_view(request):
    """Logs out of Database Manager session."""
    if "db_manager_authenticated" in request.session:
        del request.session["db_manager_authenticated"]
    messages.info(request, "Logged out of Database Manager.")
    return redirect("db_manager_index")


@require_http_methods(["POST"])
def db_manager_create_view(request):
    """Creates a new database and runs migrations with optional bootstrap admin."""
    if not is_authenticated_db_manager(request):
        messages.error(request, "Authentication required.")
        return redirect("db_manager_index")

    db_name = request.POST.get("db_name", "").strip().lower()
    seed_bootstrap = request.POST.get("seed_bootstrap") == "on"

    if not db_name:
        messages.error(request, "Database name cannot be empty.")
        return redirect("db_manager_index")

    try:
        result = create_database(db_name, seed_bootstrap=seed_bootstrap)
        bootstrap_msg = (
            " Temporary bootstrap account (admin / admin) is ready for first login."
            if result.get("bootstrap_created")
            else ""
        )
        messages.success(
            request,
            f"⚡ Database '{db_name}' created successfully! All migrations applied.{bootstrap_msg}"
        )
    except Exception as e:
        logger.error("Database creation failed: %s", str(e))
        messages.error(request, f"Failed to create database '{db_name}': {str(e)}")

    return redirect("db_manager_index")


@require_http_methods(["POST"])
def db_manager_drop_view(request):
    """Drops a database after verifying Master Password."""
    if not is_authenticated_db_manager(request):
        messages.error(request, "Authentication required.")
        return redirect("db_manager_index")

    db_name = request.POST.get("db_name", "").strip().lower()
    confirm_password = request.POST.get("confirm_master_password", "").strip()

    if not verify_master_password(confirm_password):
        messages.error(request, "Master Password verification failed. Database was not dropped.")
        return redirect("db_manager_index")

    try:
        drop_database(db_name)
        messages.success(request, f"🗑️ Database '{db_name}' has been completely dropped.")
    except Exception as e:
        logger.error("Failed to drop database '%s': %s", db_name, str(e))
        messages.error(request, f"Failed to drop database '{db_name}': {str(e)}")

    return redirect("db_manager_index")
