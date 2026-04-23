// Exit-reason display alias helper.
//
// S4.1 (Prompt 34 Commit D): Prompt 27D renamed the trade_manager's
// force-close label from "eod_close_spy" to "eod_force_close" when
// the rule was generalized beyond SPY mean_reversion. The trade
// table rows written before that rename carry the old string. The
// claim in management/trade_manager.py:258 was that the UI rendered
// them via a "legacy alias" -- but no alias existed. This is that
// alias. The DB values are preserved verbatim for audit trail; this
// helper only affects display.
//
// Keep alias values in sync with any future renames of exit-reason
// strings. A centralized exit-reason registry would be a cleaner
// long-term pattern if we accumulate more renames.

export function formatExitReason(reason: string | null | undefined): string {
    if (reason === null || reason === undefined || reason === "") {
        return "—";
    }
    // Historical alias: pre-Prompt-27D rows carry "eod_close_spy"
    // for what is now called "eod_force_close". Display using the
    // current name for consistency in the UI and analytics rollups.
    if (reason === "eod_close_spy") {
        return "eod_force_close";
    }
    return reason;
}
