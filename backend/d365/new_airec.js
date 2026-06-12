// D365 command-bar handler: opens the AI Recommendation pop-up for the current Case.
// Wire this to a Case command-bar button -> Function: openRecommendation, Param: PrimaryControl.

function openRecommendation(primaryControl) {
    // current Case id, e.g. "{0000...}" -> strip braces
    var caseId = primaryControl.data.entity.getId().replace(/[{}]/g, "");

    Xrm.Navigation.navigateTo(
        {
            pageType: "webresource",
            webresourceName: "new_airec_dialog.html",   // <- use the EXACT name after upload (publisher prefix)
            data: caseId                                  // passed to the dialog as ?data=<caseId>
        },
        {
            target: 2,        // 2 = dialog (modal)
            position: 1,      // 1 = center
            width: 560,
            height: 640
        }
    ).catch(function (e) {
        Xrm.Navigation.openAlertDialog({ text: "Could not open the recommendation dialog: " + e.message });
    });
}

/*
  ROBUST FALLBACK (if your org's content-security policy blocks the external fetch
  in new_airec_dialog.html): instead of fetching the backend, read the saved note
  via the D365 Web API (same-origin) inside the dialog. Replace the fetch(...) block
  in new_airec_dialog.html with:

    parent.Xrm.WebApi.retrieveMultipleRecords(
      "annotation",
      "?$select=notetext&$top=1&$orderby=createdon desc" +
      "&$filter=_objectid_value eq " + caseId +
      " and subject eq 'AI Support Recommendation'"
    ).then(function (res) {
      var rows = res.entities || [];
      el.innerHTML = rows.length && rows[0].notetext
        ? rows[0].notetext
        : '<div class="err">No recommendation saved for this case yet.</div>';
    }).catch(function (e) {
      el.innerHTML = '<div class="err">Could not load: ' + e.message + '</div>';
    });

  This needs no backend call and no CORS/CSP exception, but it only shows the note
  the poller already saved (which it does within ~1 minute of case creation).
*/
