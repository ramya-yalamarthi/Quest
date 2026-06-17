// D365 web resource for the AI Recommendation pop-up.
//  * openRecommendation(primaryControl)  -> wire to the "AI Recommendation" command-bar button.
//  * onCaseFormLoad(executionContext)     -> register on the Case form OnLoad for the AUTO pop-up.

var AIREC_DIALOG = "new_new_airec_dialog";   // <- EXACT HTML web resource SCHEMA Name (the "Name" column, not the display name)

function _openDialog(caseId) {
    return Xrm.Navigation.navigateTo(
        { pageType: "webresource", webresourceName: AIREC_DIALOG, data: caseId },
        { target: 2, position: 1, width: 560, height: 640, title: " " }   // 2 = modal dialog, centered; blank title (space) to hide the schema-name header
    );
}

// Command-bar button handler.
function openRecommendation(primaryControl) {
    var caseId = primaryControl.data.entity.getId().replace(/[{}]/g, "");
    _openDialog(caseId).catch(function (e) {
        Xrm.Navigation.openAlertDialog({ text: "Could not open the recommendation: " + e.message });
    });
}

// Case form OnLoad: auto-open the pop-up as soon as the AI note is ready.
// Polls every 4s for up to ~4 minutes, then pops the dialog ONCE per case per session.
function onCaseFormLoad(executionContext) {
    var formContext = executionContext.getFormContext();

    var attempts = 0;
    function check() {
        attempts++;
        // Re-read the id every loop: on a NEW case it's empty until the user
        // saves; once saved, getId() returns the id and we start looking for
        // the AI note -- so no manual Refresh is needed after creating a case.
        var id = formContext.data.entity.getId();
        if (!id) {
            if (attempts < 90) setTimeout(check, 4000);   // not saved yet -> wait
            return;
        }
        var caseId = id.replace(/[{}]/g, "");
        Xrm.WebApi.retrieveMultipleRecords(
            "annotation",
            "?$select=annotationid&$top=1&$filter=_objectid_value eq " + caseId +
            " and subject eq 'AI Support Recommendation'"
        ).then(function (res) {
            if (res.entities && res.entities.length) {
                _openDialog(caseId);                   // note is ready -> pop it up (and stop)
            } else if (attempts < 90) {
                setTimeout(check, 4000);               // not ready yet -> check again in 4s
            }
        }).catch(function () {
            if (attempts < 90) setTimeout(check, 4000);
        });
    }
    // Defer the first check so the dialog opens AFTER the form finishes loading
    // (D365 silently ignores navigateTo called during the OnLoad phase).
    setTimeout(check, 2000);
}
