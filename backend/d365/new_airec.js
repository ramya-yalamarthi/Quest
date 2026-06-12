// D365 web resource for the AI Recommendation pop-up.
//  * openRecommendation(primaryControl)  -> wire to the "AI Recommendation" command-bar button.
//  * onCaseFormLoad(executionContext)     -> register on the Case form OnLoad for the AUTO pop-up.

var AIREC_DIALOG = "new_airec_dialog.html";   // <- use the EXACT web resource name after upload (publisher prefix)

function _openDialog(caseId) {
    return Xrm.Navigation.navigateTo(
        { pageType: "webresource", webresourceName: AIREC_DIALOG, data: caseId },
        { target: 2, position: 1, width: 560, height: 640 }   // 2 = modal dialog, centered
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
// Polls every 20s for up to ~3 minutes, then pops the dialog ONCE per case per session.
function onCaseFormLoad(executionContext) {
    var formContext = executionContext.getFormContext();
    var id = formContext.data.entity.getId();
    if (!id) return;                                   // unsaved/new form -> nothing yet
    var caseId = id.replace(/[{}]/g, "");
    var key = "airec_shown_" + caseId;
    try { if (window.sessionStorage.getItem(key)) return; } catch (e) {}

    // Poll quickly (every 4s, up to ~4 min) so the pop-up shows almost the
    // instant the note is ready.
    var attempts = 0;
    function check() {
        attempts++;
        Xrm.WebApi.retrieveMultipleRecords(
            "annotation",
            "?$select=annotationid&$top=1&$filter=_objectid_value eq " + caseId +
            " and subject eq 'AI Support Recommendation'"
        ).then(function (res) {
            if (res.entities && res.entities.length) {
                try { if (window.sessionStorage.getItem(key)) return; window.sessionStorage.setItem(key, "1"); } catch (e) {}
                _openDialog(caseId);                   // note is ready -> pop it up
            } else if (attempts < 60) {
                setTimeout(check, 4000);               // not ready yet -> check again in 4s
            }
        }).catch(function () { /* ignore transient errors */ });
    }
    check();
}
