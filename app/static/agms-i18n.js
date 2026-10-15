/* AGMS language selector. English is the default; German is optional per browser. */
(()=>{
'use strict';
const translations={
'Willkommen zurück':'Welcome back',
'Melde dich an, um deine Homepages zu öffnen.':'Sign in to access your homepages.',
'E-Mail / Benutzername':'Email / username','Passwort':'Password','Anmelden →':'Sign in →',
'Registrieren':'Sign up','Passwort vergessen?':'Forgot password?',
'Konto erstellen':'Create account','Deine eigene Homepage und dein eigenes Team.':'Your own homepage and team.',
'Benutzername':'Username','E-Mail-Adresse':'Email address','Passwort (mindestens 16 Zeichen)':'Password (at least 16 characters)',
'Bereits registriert? Zum Login':'Already registered? Sign in',
'Passwort vergessen':'Forgot password','Zur Anmeldung':'Back to sign in',
'Neues Passwort setzen':'Set new password','Neues Passwort (mind. 16 Zeichen)':'New password (min. 16 characters)',
'Team-Einladung':'Team invitation','Bitte mit der eingeladenen E-Mail-Adresse anmelden oder registrieren.':'Please sign in or register using the invited email address.',
'Einladung annehmen':'Accept invitation','Zum Login':'Go to sign in',
'E-Mail bestätigen':'Verify email','Neue E-Mail bestätigen':'Verify new email',
'Bestätige die neue E-Mail-Adresse für dein AGMS-Konto.':'Confirm the new email address for your AGMS account.',
'E-Mail-Wechsel bestätigen':'Confirm email change','Zurück zum Profil':'Back to profile',
'Mein Profil':'My profile','← Dashboard':'← Dashboard','Profilbild (PNG, JPG, WebP)':'Profile picture (PNG, JPG, WebP)',
'Profilbild entfernen':'Remove profile picture','Profil speichern':'Save profile','E-Mail-Adresse ändern':'Change email address',
'Aktuelle E-Mail:':'Current email:','Neue E-Mail-Adresse':'New email address',
'Aktuelles Passwort zur Bestätigung':'Current password for confirmation','Bestätigungslink senden':'Send confirmation link',
'Infrastrukturübersicht':'Infrastructure overview','Dein Homelab. Alles im Blick.':'Your homelab at a glance.',
'Systeme, Dienste und Ressourcen an einem Ort.':'Systems, services and resources in one place.',
'Homepages & Navigation bearbeiten ↗':'Manage homepages & navigation ↗',
'System':'System','Originaloberfläche innerhalb von AGMS':'Original interface inside AGMS',
'Adresse ändern':'Change address','Neu laden':'Reload','Extern öffnen ↗':'Open externally ↗',
'Adresse des Systems (HTTPS oder lokale HTTP-Adresse)':'System address (HTTPS or local HTTP address)',
'Übernehmen':'Apply','Warte auf Daten …':'Waiting for data …',
'● Verbindung wird geprüft':'● Checking connection',
'HOMEPAGE':'HOMEPAGE','＋ Homepage':'＋ Homepage','Umbenennen':'Rename','Löschen':'Delete',
'Übersicht':'Overview','MEINE GRUPPEN':'MY GROUPS','＋ WebUI hinzufügen':'＋ Add web UI',
'♧ Team verwalten':'♧ Manage team','♛ Premium verwalten':'♛ Manage premium',
'↪ Abmelden':'↪ Sign out','ÜBERSICHT':'OVERVIEW','Meine Homepage':'My homepage',
'Profil':'Profile','Benachrichtigungen':'Notifications','Bearbeiten':'Edit',
'Weboberflächen':'Web interfaces','Deine Dienste, gruppiert und direkt erreichbar.':'Your services, grouped and easy to access.',
'Suche':'Search','Ansicht':'View','Kacheln':'Tiles','Liste':'List',
'← Zurück':'← Back','⛶ Vollbild':'⛶ Fullscreen','⤢ Verkleinern':'⤢ Minimize',
'Gruppen & WebUIs verwalten':'Manage groups & web UIs',
'Verwalte deine Weboberflächen direkt in der jeweiligen Gruppe. Änderungen werden erst mit „Speichern“ übernommen.':'Manage your web interfaces in each group. Changes take effect when you click Save.',
'Speichern':'Save','Abbrechen':'Cancel','Homepage-Team':'Homepage team',
'＋ Per E-Mail einladen':'＋ Invite by email','Schließen':'Close',
'Falls die Anwendung keine Einbettung erlaubt, öffne sie extern. HTTPS-Seiten können interne HTTP-Adressen blockieren.':'If embedding is blocked, open the app externally. HTTPS sites may block internal HTTP addresses.',
'Benutzer & Proxy-Freigaben':'Users & proxy approvals','Zurück':'Back',
'Benutzerkonten':'User accounts','Proxy-Freigaben':'Proxy approvals',
'Anfragen freigeben, ablehnen oder Freigaben widerrufen.':'Approve or reject requests, or revoke existing approvals.',
'Freigeben':'Approve','Ablehnen':'Reject','Freigabe entfernen':'Revoke approval','Anfrage entfernen':'Remove request',
'Benutzer löschen':'Delete user','Verifiziert':'Verified','Nicht verifiziert':'Not verified',
'Freigegeben':'Approved','Ausstehend':'Pending','Abgelehnt':'Rejected',
'Entscheidung gespeichert':'Decision saved','Benutzer gelöscht':'User deleted',
'Benutzer (kostenlos)':'User (free)','Ablehnungsgrund:':'Rejection reason:',
'★ Favoriten':'★ Favorites','Keine Treffer':'No results','Noch keine Einträge vorhanden.':'No entries yet.',
'Weboberfläche':'Web interface','Gruppe öffnen':'Open group',
'● Online':'● Online','● Offline':'● Offline','● Prüfe …':'● Checking …',
'● Nicht prüfbar':'● Cannot check','Noch keine Weboberflächen. Über „WebUI hinzufügen“ kannst du deinen ersten Dienst anlegen.':'No web interfaces yet. Use Add web UI to add your first service.',
'Keine passenden Benutzer.':'No matching users.','Keine passenden Proxy-Einträge.':'No matching proxy entries.',
'Keine Proxy-Anfragen vorhanden.':'No proxy requests.',
'Keine Bearbeitungsrechte':'No editing permission',
'WebUI-Adresse':'Web UI address','Als Favorit anzeigen':'Show as favorite',
'Gruppen':'Groups','Gruppe':'Group','Name':'Name','Farbe':'Color','Icon':'Icon',
'Öffnen':'Open','Entfernen':'Remove','Erstellen':'Create','Hinzufügen':'Add',
'Neue':'New','Status':'Status','Einstellungen':'Settings',
'Abmelden':'Sign out','Benutzer':'Users','Passwort ändern':'Change password',
'Erfolgreich gespeichert':'Saved successfully'
};
const placeholders={
'Gruppen und WebUIs suchen …':'Search groups and web UIs …',
'Benutzername, E-Mail oder Rolle suchen …':'Search username, email or role …',
'Adresse, Antragsteller oder Status suchen …':'Search address, requester or status …',
'Name der neuen Homepage':'Name of the new homepage'
};
Object.assign(translations,{
'Bitte bestätige deine E-Mail-Adresse über den Link in deinem Postfach.':'Please confirm your email using the link in your inbox.',
'Registrierung fehlgeschlagen':'Registration failed',
'Erfolgreich. Bitte bei Bedarf anmelden.':'Success. Please sign in if needed.',
'Verbindung fehlgeschlagen':'Connection failed','Fehler':'Error',
'Einladung angenommen. Homepage ist jetzt verfügbar.':'Invitation accepted. The homepage is now available.',
'Bitte zuerst anmelden.':'Please sign in first.',
'Neue E-Mail-Adresse bestätigt. Ab sofort damit anmelden.':'New email address confirmed. You can now sign in with it.',
'Nur für Administratoren':'Administrators only',
'Proxy-Freigaben konnten nicht geladen werden':'Could not load proxy approvals',
'Benutzerverwaltung nur für Administratoren verfügbar':'User administration is only available to administrators',
'Bitte einen Ablehnungsgrund eingeben.':'Please enter a rejection reason.',
'Maximal 1000 Zeichen erlaubt.':'Maximum 1000 characters.',
'Tier gespeichert':'Tier saved',
'Änderung fehlgeschlagen':'Update failed',
'Benutzer gelöscht':'User deleted',
'Entfernen fehlgeschlagen':'Removal failed',
'Proxy-Eintrag entfernt':'Proxy entry removed',
'Noch keine Benachrichtigungen':'No notifications',
'Keine Benachrichtigungen':'No notifications',
'Als gelesen markieren':'Mark as read',
'Weboberfläche':'Web interface','Gruppe öffnen':'Open group',
'Nicht prüfbar':'Cannot check',
'Export JSON':'Export JSON','Import JSON':'Import JSON'
});
Object.assign(translations,{"Adminbereiche":"Admin sections","Adminbereich": "Admin Panel", "Proxy-Anfragen": "Proxy requests", "Ticket erstellen": "Create Ticket", "Betreff": "Subject", "Kategorie": "Category", "Problem": "Problem", "Idee": "Idea", "Wunsch": "Wish", "Sonstiges": "Other", "Ticket senden": "Submit ticket", "Ticket erstellt. Vielen Dank!": "Ticket created. Thank you!", "Ticket konnte nicht erstellt werden. Bitte erneut versuchen.": "Could not create ticket. Please try again.", "Keine Tickets gefunden.": "No tickets found.", "Tickets konnten nicht geladen werden.": "Could not load tickets.", "Betreff, Kategorie oder Absender suchen": "Search subject, category or requester", "Tickets durchsuchen": "Search tickets", "Benutzer durchsuchen": "Search users", "Proxy-Anfragen durchsuchen": "Search proxy requests", "Benutzer und alle eigenen Homepages löschen?": "Delete this user and all their homepages?", "Dieses Proxy-Ziel freigeben?": "Approve this proxy destination?", "Freigabe widerrufen? Bestehende Weboberflächen verlieren den Proxy-Zugriff.": "Revoke this approval? Existing web interfaces will lose proxy access.", "Diese Anfrage endgültig entfernen?": "Permanently remove this request?", "Benutzer konnte nicht gelöscht werden.": "Could not delete user.", "Entscheidung konnte nicht gespeichert werden.": "Could not save decision.", "Tier 0: 1 Homepage · Tier 1: 3 · Tier 2: 5 · Tier 3: 10": "Tier 0: 1 homepage · Tier 1: 3 · Tier 2: 5 · Tier 3: 10"});
Object.assign(translations,{"Beschreibung":"Description","Keine Beschreibung vorhanden.":"No description provided.","Ticket konnte nicht geladen werden.":"Could not load ticket.","Nummer, Betreff, Kategorie oder Absender suchen":"Search number, subject, category or requester"});
Object.assign(translations,{"Meine Tickets":"My tickets","Offen":"Open","In Bearbeitung":"In progress","Gelöst":"Resolved","Warten auf Rückmeldung":"Waiting for feedback","Kommentare":"Comments","Kommentar":"Comment","Kommentar hinzufügen":"Add comment","Status speichern":"Save status","Noch keine Kommentare.":"No comments yet.","Bitte einen Kommentar eingeben.":"Please enter a comment.","Neues Ticket eingegangen":"New ticket received","Ticket-Antwort eingegangen":"Ticket reply received","Ticket gelöst":"Ticket resolved","Weitere Informationen zu deinem Ticket werden benötigt":"More information is needed for your ticket","Bitte vor dem Anfordern einer Rückmeldung oder dem Lösen einen Kommentar hinzufügen":"Add a comment before requesting feedback or resolving a ticket","Dieses Ticket wartet nicht auf Rückmeldung":"This ticket is not waiting for feedback","Kommentar muss 1–10000 Zeichen enthalten":"Comment must be 1-10000 characters"});
Object.assign(translations,{"Passwortmanager einrichten":"Password manager setup","Füge die folgenden Adressen zum Tresoreintrag dieses Dienstes hinzu. Wähle für jede Adresse die URI-Erkennung „Beginnt mit“. Behalte die ursprüngliche Website-Adresse bei.":"Add the following URLs to this service's vault entry. Set URI match detection to Starts with for each URL. Keep the original website URL.","Website-Adresse":"Website URL","AGMS-Adresse":"AGMS URL","Proxy-Adresse":"Proxy URL","Kopieren":"Copy","Kopiert":"Copied","Bitte die Adresse manuell kopieren.":"Please copy the URL manually.","Vorschläge und das Einblenden des Menüs werden von deiner Browser-Erweiterung gesteuert.":"Suggestions and menu visibility are controlled by your browser extension.","WebUI nicht gefunden":"WebUI not found"});
Object.assign(translations,{"Dienst": "Service", "Allgemeines Ticket": "General ticket", "Priorität": "Priority", "Niedrig": "Low", "Normal": "Normal", "Hoch": "High", "Dringend": "Urgent", "Screenshots": "Screenshots", "Bis zu 3 PNG-, JPEG- oder WebP-Bilder, jeweils 2 MB.": "Up to 3 PNG, JPEG or WebP images, 2 MB each.", "Bis zu 3 Screenshots auswählen": "Choose up to 3 screenshots", "Jeder Screenshot darf höchstens 2 MB groß sein": "Each screenshot must be at most 2 MB", "Screenshots müssen PNG, JPEG oder WebP sein": "Screenshots must be PNG, JPEG or WebP", "Screenshot konnte nicht gelesen werden.": "Could not read screenshot.", "Ungültiger Screenshot": "Invalid screenshot", "Ein Ticket darf höchstens 10 Screenshots haben": "A ticket can have at most 10 screenshots", "Ticket anzeigen": "View ticket", "Zuständig": "Assigned to", "Nicht zugewiesen": "Unassigned", "Ticket verwalten": "Manage ticket", "Änderungen speichern": "Save changes", "Ungültige Ticket-Zuweisung": "Invalid ticket assignment", "Administrator auswählen": "Choose an administrator", "Einen zugänglichen Dienst auswählen": "Choose an accessible service", "Ungültige Priorität": "Invalid priority", "Globale Suche": "Global search", "Alles durchsuchen": "Search everything", "Dienste, Gruppen und Tickets durchsuchen": "Search services, groups and tickets", "Ticket": "Ticket", "Gruppe": "Group", "Benachrichtigungseinstellungen": "Notification settings", "Ticketaktivität in der Glocke": "Ticket activity in the bell", "Proxy- und Teamaktivität in der Glocke": "Proxy and team activity in the bell", "Ticketaktivität per E-Mail": "Ticket activity by email", "E-Mail-Sprache": "Email language", "E-Mail-Benachrichtigungen benötigen eingerichtetes SMTP und eine bestätigte E-Mail-Adresse.": "Email notifications require configured SMTP and a verified email address.", "Ungültige Benachrichtigungseinstellungen": "Invalid notification settings", "Statusübersicht": "Status overview", "Erreichbarkeit der Dienste über alle deine Homepages.": "Service reachability across your homepages.", "Dienste durchsuchen": "Search services", "Alle Homepages": "All homepages", "Homepage": "Homepage", "Status aktualisieren": "Refresh status", "Online": "Online", "Eingeschränkt": "Degraded", "Offline": "Offline", "Ungeprüft": "Not checked", "Dienste werden geprüft…": "Checking services…", "Private Adressen werden nicht geprüft": "Private addresses are not checked", "Dieser Port wird nicht geprüft": "This port is not checked", "Dieser Dienst konnte nicht geprüft werden": "Could not check this service", "Keine Dienste gefunden.": "No services found.", "Erreichbarkeit vom AGMS-Server geprüft. Antworten mit erforderlicher Anmeldung gelten als erreichbar.": "Reachability checked from the AGMS server. Login-required responses count as reachable.", "Problem melden": "Report a problem", "Anfrage fehlgeschlagen": "Request failed", "Ticketdaten sind zu groß": "Ticket payload is too large", "● Eingeschränkt": "● Degraded", "Suchanfrage ist zu lang": "Search is too long", "Screenshot nicht gefunden": "Screenshot not found"});
Object.assign(translations,{"Keine neuen Benachrichtigungen":"No new notifications"});
Object.assign(translations,{"Dienststatus":"Service status","Kostenlos · 1 Homepage":"Free · 1 Homepage"});
Object.assign(translations,{"Upload abgelehnt. Bitte kleinere Screenshots versuchen.":"Upload rejected. Try smaller screenshots."});
Object.assign(translations,{"Weitere Treffer vorhanden. Bitte die Suche eingrenzen.":"More matches exist. Refine your search."});
Object.assign(translations,{"Deine Statusseiten und ausgewählten Monitore, nach Kategorien geordnet.": "Your status pages and selected monitors, organized by category.", "Statuseintrag hinzufügen": "Add status entry", "Kuma aktualisieren": "Refresh Kuma", "Statuseintrag konfigurieren": "Configure status entry", "Öffentliche Statusseiten-URL": "Public status page URL", "Monitore laden": "Load monitors", "Statusseite wird geladen…": "Loading status page…", "Füge eine veröffentlichte Kuma-Statusseite hinzu, um zu beginnen.": "Add a published Kuma status page to get started.", "Keine veröffentlichten Monitore gefunden.": "No published monitors found.", "Wähle einzelne Monitore oder lasse alle abgewählt.": "Choose individual monitors or leave all unselected.", "Einige ausgewählte Monitore sind nicht mehr veröffentlicht.": "Some selected monitors are no longer published.", "Status aktualisiert. Kuma kann Ergebnisse bis zu fünf Minuten zwischenspeichern.": "Status updated. Kuma may cache results for up to five minutes.", "Verwende die vollständige öffentliche URL mit /status/page-slug. Lasse alle Monitore abgewählt, um die ganze Seite anzuzeigen.": "Use the full public URL ending in /status/page-slug. Leave all monitors unselected to show the entire page.", "Lade vor dem Speichern einer Monitorauswahl die Monitore.": "Load monitors before saving a monitor selection.", "Wartung": "Maintenance", "Ausstehend": "Pending", "Kuma konnte nicht geladen werden. Verwende eine veröffentlichte Statusseite mit öffentlicher Adresse und gültigem TLS-Zertifikat; Weiterleitungen werden nicht verfolgt.": "Cannot load Kuma. Use a published status page on a public address with a valid TLS certificate; redirects are not followed."});
Object.assign(translations,{"Titel": "Title", "Gib eine öffentliche Kuma-Statusseiten-URL ein": "Enter a public Kuma status page URL", "Ungültige Statusseiten-URL": "Invalid status page URL", "Verwende die vollständige öffentliche URL mit /status/page-slug": "Use the full public URL ending in /status/page-slug", "Wähle bis zu 30 Statuseinträge": "Choose up to 30 status entries", "Gib einen Titel und eine Kategorie ein": "Enter a title and category", "Ungültige Monitorauswahl": "Invalid monitor selection"});
Object.assign(translations,{"Proxy benötigt eine HTTPS-Adresse ohne Zugangsdaten oder Fragment":"Proxy requires an HTTPS URL without credentials or a fragment"});
Object.assign(translations,{"Verfügbarkeit · 24h":"Uptime · 24h","Keine Verfügbarkeitsdaten":"No uptime data"});
Object.assign(translations,{"Kategorieüberschrift": "Category heading", "Eigener Name": "Custom name", "Monitor von der Statusseite": "Monitor from status page", "Monitor im Kartenkopf": "Header monitor", "Monitore laden und einen Monitor für den Kartenkopf auswählen": "Load monitors and select a header monitor", "Der ausgewählte Monitor ist nicht mehr veröffentlicht": "Selected monitor is no longer published", "Ungültiger Monitor für den Kartenkopf": "Invalid header monitor"});
const reverse=Object.fromEntries(Object.entries(translations).map(([de,en])=>[en,de]));
const placeholderReverse=Object.fromEntries(Object.entries(placeholders).map(([de,en])=>[en,de]));
const readLanguage=()=>{try{return localStorage.getItem('agms-language')==='de'?'de':'en'}catch{return'en'}};
let language=readLanguage(),busy=false,scheduled=false;
window.agmsTranslate=text=>language==='de'?(reverse[text]||text):(translations[text]||text);
const originalText=new WeakMap(),lastText=new WeakMap(),originalAttrs=new WeakMap();
const skip=node=>node.parentElement?.closest('script,style,textarea,code,pre,[data-agms-i18n-ignore]')||false;
function translateText(node){
 if(skip(node))return;
 const value=node.nodeValue||'',trim=value.trim();
 if(!trim)return;
 let source=originalText.get(node);
 if(source===undefined||lastText.get(node)!==trim){source=reverse[trim]||trim;originalText.set(node,source)}
 const result=language==='de'?source:(translations[source]||source);
 if(trim!==result)node.nodeValue=value.replace(trim,result);
 lastText.set(node,result);
}
function translateAttributes(element){
 if(element.closest('[data-agms-i18n-ignore]'))return;
 for(const attr of ['placeholder','title','aria-label']){
  if(!element.hasAttribute(attr))continue;
  let originals=originalAttrs.get(element);
  if(!originals){originals={};originalAttrs.set(element,originals)}
  const current=element.getAttribute(attr);
  if(!(attr in originals))originals[attr]=placeholderReverse[current]||reverse[current]||current;
  const source=originals[attr],value=language==='de'?source:(placeholders[source]||translations[source]||source);
  if(current!==value)element.setAttribute(attr,value);
 }
}
function translateTree(root){
 if(root.nodeType===3){translateText(root);return}
 if(root.nodeType!==1&&root.nodeType!==9)return;
 if(root.nodeType===1)translateAttributes(root);
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT);
 while(walker.nextNode()){const n=walker.currentNode;if(n.nodeType===3)translateText(n);else translateAttributes(n)}
}
function apply(){
 if(busy)return;
 busy=true;
 try{document.documentElement.lang=language;translateTree(document.body);const sel=document.getElementById('agmsLanguage');if(sel)sel.value=language}
 finally{busy=false}
}
function schedule(){if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;apply()})}
function mount(){
 if(document.getElementById('agmsLanguage'))return;
 const wrapper=document.createElement('label');
 wrapper.dataset.agmsI18nIgnore='';
 wrapper.style.cssText='display:inline-flex;align-items:center;gap:6px;z-index:1000;font-size:13px;white-space:nowrap';
 const select=document.createElement('select');select.id='agmsLanguage';select.setAttribute('aria-label','Language / Sprache');
 select.style.cssText='padding:7px 9px;border-radius:8px;background:#15253d;color:#fff;border:1px solid #52647c;max-width:140px';
 for(const [value,name] of [['en','English'],['de','Deutsch']]){const o=document.createElement('option');o.value=value;o.textContent=name;select.append(o)}
 select.value=language;
 select.addEventListener('change',()=>{language=select.value;try{localStorage.setItem('agms-language',language)}catch{};apply()});
 wrapper.append(select);
 const host=document.querySelector('.web-top-actions')||document.querySelector('.top')||document.querySelector('header');
 if(host){host.append(wrapper)}
 else{wrapper.style.cssText+=';position:fixed;right:12px;top:12px;padding:4px;border-radius:9px;background:#101c2e';document.body.append(wrapper);document.body.style.paddingTop='max(55px, env(safe-area-inset-top))'}
}
function init(){
 mount();apply();
 new MutationObserver(()=>{if(!busy)schedule()}).observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','title','aria-label']});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
