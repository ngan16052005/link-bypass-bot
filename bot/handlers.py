"""
Facade module cho bot package.
Re-export toàn bộ các handler và hằng số từ các module con để đảm bảo tương thích ngược 100%.
"""

from .texts import (
    TASK_SHORTENER_DOMAINS,
    WELCOME_MESSAGE,
    HELP_MESSAGE,
    SERVICES_MESSAGE,
    BATCH_MESSAGE,
    KEY_INFO_MESSAGE,
    REPORT_INFO_MESSAGE,
    get_dashboard_text
)
from .fsub import check_user_fsub
from .user_commands import (
    start_command,
    menu_command,
    help_command,
    services_command,
    batch_command,
    myid_command,
    ref_command,
    history_command,
    key_command,
    do_grab_key
)
from .admin_commands import (
    stats_command,
    broadcast_command,
    reports_command,
    clear_reports_command,
    claimadmin_command,
    setvip_command,
    removevip_command,
    viplist_command,
    setchannel_command,
    togglefsub_command
)
from .callbacks import callback_router
from .message_handlers import (
    handle_message,
    handle_document,
    inline_query_handler
)

__all__ = [
    "TASK_SHORTENER_DOMAINS",
    "WELCOME_MESSAGE",
    "HELP_MESSAGE",
    "SERVICES_MESSAGE",
    "BATCH_MESSAGE",
    "KEY_INFO_MESSAGE",
    "REPORT_INFO_MESSAGE",
    "get_dashboard_text",
    "check_user_fsub",
    "start_command",
    "menu_command",
    "help_command",
    "services_command",
    "batch_command",
    "myid_command",
    "ref_command",
    "history_command",
    "key_command",
    "do_grab_key",
    "stats_command",
    "broadcast_command",
    "reports_command",
    "clear_reports_command",
    "claimadmin_command",
    "setvip_command",
    "removevip_command",
    "viplist_command",
    "setchannel_command",
    "togglefsub_command",
    "callback_router",
    "handle_message",
    "handle_document",
    "inline_query_handler"
]
