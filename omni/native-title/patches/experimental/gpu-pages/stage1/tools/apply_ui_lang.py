#!/usr/bin/env python3
"""OMNI_UI_LANG_V1 (2026-11-16): Omni's own UI (menus, settings, notices, hint bar) in Spanish, French, German and
Portuguese - stage 1.

What the user sees
  - With the PS5 system language set to Spanish / French / German / Portuguese (any regional variant), Browser settings,
    Options, the page menu, Site settings and every other controller panel (OmniFxPanel), the notices (toast) and the
    bottom hint bar are drawn in that language - for the ~200 strings in the built-in table. Anything not in the
    table stays English, exactly as before. English consoles see no change at all (the table stays empty).
  - Browser settings has a new first row "Language" (stepper): Automatic / English / Espanol / Francais / Deutsch /
    Portugues (native names). The choice is saved in /data/omni/ui-lang.txt ("auto", "en", "es", ...) and applies at
    once (the panel redraws translated). Automatic shows the detected language as the row's dim detail.
  - Translations can be corrected or added without a rebuild: /data/omni/lang/<code>.txt, UTF-8, one entry per line
        English text<TAB>Translation
        Saved for later: *<TAB>Guardado para después: *        (a trailing * on both sides: prefix entry)
    '#' starts a comment line. File entries override the built-in ones. A language without a built-in table works
    from the file alone (e.g. "it" in ui-lang.txt, or an Italian console on Automatic, with lang/it.txt).

How the system language reaches the title
  sceSystemServiceParamGetInt(SCE_SYSTEM_SERVICE_PARAM_ID_LANG = 1, &v) is NOT in the launch title's import list
  (titlefix-rc6/merge/imports-launch.txt has only sceSystemServiceHideSplashScreen / LoadExec from that library), and
  the title link gate requires the import list to stay exactly the same. So it is resolved at run time with
  dlopen("libSceSystemService.sprx") + dlsym, the same way OmniMain.cpp already reaches the real
  sceSystemServiceLoadExec (dlopen/dlsym add no import: they are already used by the title), with
  dlsym(RTLD_DEFAULT, ...) as the second try (OmniCrash.h's pattern). Not found / failing -> English, and the
  Language row still lets the user pick. v -> code: SCE_SYSTEM_PARAM_LANG_* order (0 ja, 1 en-US, 2 fr, 3 es, 4 de,
  5 it, 6 nl, 7 pt-PT, ... 17 pt-BR, 18 en-GB, 20 es-LA, 22 fr-CA, ...).

Where the translation happens (drawing chokepoints only - no call site changes, no logic changes)
  The code compares English texts in several places (title == "Apps", r.label == "Close tab", status == ours, hosts
  in r.label), so nothing stored is translated: omniTr() is applied only where text is drawn or measured.
    OmniBrowser.cpp   omniHintItemW + omniHintDraw (hint labels: width and drawing use the same translated text),
                      omniHints' dim note, omniDrawToast (the shown text; the English status still drives the toast)
    OmniFeaturesPanel.h  omniFxDrawPanel: title, subtitle, corner, row label / value / detail / section prefix
    OmniBrowserSettings.h  the Language row (id 8861) and its input (before the >= 300 dispatch)
  Text width: every panel text keeps its existing maxW (longer translations end in an ellipsis exactly like long page
  titles do); hint items are measured from the translated text, so the hint bar flows as before (a German bar is
  wider: it still starts at the left and the dim note shrinks first).
  Not covered in stage 1 (stay English): screens drawn with direct omniLabel("...") calls (History, Controls guide
  table, keyboard, modal dialogs, start page HTML), notices built as "A " + x + " B", settings search matching
  (it matches the English labels).

Cost: English = one bool test per drawn text. Other languages: one hash lookup per drawn text (+ a scan of ~20
prefixes on a miss), only when the shell redraws.

Files: writes OmniUiLang.h (pure, host-tested by tools/test_ui_lang.cpp) and OmniUiLangShell.h; patches
OmniBrowser.cpp (1 include + 4 lines), OmniFeaturesPanel.h (10 lines), OmniBrowserSettings.h (3 anchors).
Each anchor is a whole line found exactly once; line endings kept per file; re-run prints "already".

=== OMNI_UI_LANG_V1_R2 (2026-11-16): stage 2 ===
What changes for the user (English: nothing - every new path is gated on a loaded table)
  - Every screen drawn with direct omniLabel("...") calls is translated: History, Clear history, the address bar
    placeholder, the keyboard's sites page, the Controls guide title and section tabs, Display settings, the find bar,
    the QR / screenshot / tab switcher / quick access screens, error and HTTPS-only pages (title + chips), modal
    login prompts' fixed lines. Also the keyboard hint bar and the Controls guide table (action + note + section line).
  - Browser settings search matches the English label (as before) AND the label shown (translated; case and accents
    folded: "configuracion" finds "Configuracoes"/"Configuración"), the best of the two decides the order.
  - The built-in table grows to ~700 strings (es / fr / de / pt-BR), a glossary keeps the terms consistent (below).
How literals are told apart from dynamic text (no call site changes)
  omniLabel gets a second overload taking `const char*`. C++ picks it for exactly the calls whose text is a
  const char*: string literals ("History"), ternaries of literals, and the shell's constant tables
  (OCH::sectionTitle, OHCT::toggleWord, OOR::kBadge, OHP::rangeName ...). It translates (omniTr) and forwards to the
  std::string version. Everything held in a std::string - page titles, addresses, host names, file names, user
  words, concatenations like "No visits match " + query - picks the std::string overload and is drawn unchanged.
  Audited 2026-11-16 by compiling the tree with the const char* overload [[deprecated]]: 62 call sites resolve to it,
  all UI text or arrows ("\xe2\x96\xb2"); no .c_str() / page data among them. omniTextWidthPx deliberately gets NO
  such overload (it is called with .c_str() of user words / autofill labels): the 4 places that measure a const char*
  and then draw it with omniLabel measure omniTr(...) explicitly (Protection chip, suggestions tip, Offline badge x2).
  Texts kept in std::string are translated where they are drawn: Controls guide rows (omniTr before OCH::expand, so
  {Cross}-style tokens stay tokens), the keyboard hint labels, the "Hold" pill, the guide's page line (a format
  key "Page %d of %d ..." - Table::add rejects any translation whose printf conversions differ from the key's).
Layout (German ~30% longer)
  - omniUlFace: a translated text wider than its maxW takes the next smaller face (Body > Small > Caption,
    bold likewise, Title > BodyBold); omniLabel's own ellipsis (omniFit) handles what is still too wide. Used by the
    const char* overload (every literal with a maxW: tabs, chips, section tabs, badges), panel rows (label, value,
    tile label / value / big value) and the Controls guide action line.
  - Hint bar: omniUlHintFit, per bar, when the translated items do not fit between the screen edges: labels go to
    the Caption face, and if that is not enough every label is capped at the same width (water-filling,
    OL10::fitCap, min 24 px) with an ellipsis. Width and drawing use the same text. Reset after each bar.
  - Keyboard hint bar (flows without a right group): translated labels use the Caption face and stop at the screen
    edge (ellipsis) instead of running off it.
Glossary (es / fr / de / pt-BR) - kept by tools/test_ui_lang.cpp's glossary check
  tab: pestaña / onglet / Tab / aba          bookmark: marcador / favori / Lesezeichen / favorito
  reading list: lista de lectura / liste de lecture / Leseliste / lista de leitura
  shortcut (start page): acceso directo / raccourci / Verknüpfung / atalho     settings: ajustes / paramètres / Einstellungen / configurações
  site: sitio / site / Website / site       web page: página web / page web / Webseite / página da web
  controller: mando / manette / Controller / controle    D-pad: cruceta / croix / Steuerkreuz / direcional
  pointer: puntero / pointeur / Zeiger / ponteiro      console: consola / console / Konsole / console
  private tab: pestaña privada / onglet privé / privater Tab / aba privada    session: sesión / session / Sitzung / sessão
  start page: página de inicio / page de démarrage / Startbildschirm / página de início; home page: página principal /
  page d'accueil / Startseite / página inicial.   Imperatives: es tú, fr vous, de du, pt você.
  UNTRANSLATED (names): uBlock, uBO, Omni, Omnibloom, Bloom Core, YouTube, PlayStation, Xbox, the Downloads app
  ("Downloads", also inside paths "Downloads > ..."), Media downloads, and controller button names (Cross, Circle,
  Square, Triangle, L1..R3, Options, Create, Touchpad, A/B/X/Y...) - the guide's {Cross} tokens expand to these
  English names, so prose uses them too. English-only rows are listed in the table with no translation.
Files / anchors (R2): OmniUiLang.h + OmniUiLangShell.h rewritten (R2 content); OmniBrowser.cpp: the omniLabel
  overload + helpers before the OMNI_VIDEO_IMMERSIVE_V1 comment line; omniHintItemW / omniHintDraw (V1 lines);
  omniUlHintFit before the hint bar comment line; omniHints' head (3 lines) and its V1 note line; the keyboard hint
  label lambda; the Protection word measure; the suggestions tip measure. OmniFeaturesPanel.h: the 5 V1 row lines
  with a maxW (face shrink). OmniControlsHelpShell.h: Hold pill, section line, action/note lines, remap line, 2 draw
  lines, page line. OmniSettingsSearchShell.h: omniUlSsrView before omniSsrSearchRow, the view() call.
  OmniDlProgressShell.h / OmniOfflineRetryShell.h (if present): the kBadge measure line.
  Every anchor is a whole line, exactly once; all files are computed in memory and checked before anything is
  written. In-place upgrade: a stage-1 tree gets only the R2 edits (they anchor on the V1 lines); a fresh tree gets
  V1 then R2 in memory - both end byte-identical. Re-run prints "already OMNI_UI_LANG_V1_R2".
ORDER: run LAST in the title recipe: after apply_controls_help.py, apply_settings_search.py, apply_ui_scale.py (r4),
  apply_button_map.py (if they are in the chain) and every other OmniBrowser.cpp / OmniFeaturesPanel.h /
  OmniBrowserSettings.h patch: ... apply_yt_media_stop.py, apply_ui_scale.py, apply_button_map.py, apply_ui_lang.py.
  apply_ui_scale.py r4 rewrites the hint bar (omniHints head -> omniUisHints + a zoomed `width`, the note line's centre):
  the hint edits have a second spelling for that tree (ALT, exactly one must match), omniUlHintFit takes ui_scale's
  zoomed width, OmniUiScalePanels.h's natural-width line measures the translated note, and its Protection pill cap
  (OmniUisTextCap) measures the translated word. Running ui_lang BEFORE ui_scale breaks ui_scale's anchors: don't.
usage: apply_ui_lang.py <engine tree>
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_UI_LANG_V1'
MARK2 = 'OMNI_UI_LANG_V1_R2'
ROW_ID = 8861
root = Path(sys.argv[1]) / 'engine' / 'entry'

# ---------------------------------------------------------------------------------------------------------------
# The built-in table. (English, Spanish, French, German, Portuguese (Brazil), unsure)
# unsure = True: machine-uncertain (gender agreement with an unknown noun, or a term choice a native speaker should
# check). Spanish: Spain/neutral ("mando"). Portuguese: Brazilian ("aba", "celular", "controle").
# Keys must be the exact English bytes the code draws. Keys/translations ending in '*' are prefixes.
# ---------------------------------------------------------------------------------------------------------------
T = [
    # Language row (new)
    ('Language', 'Idioma', 'Langue', 'Sprache', 'Idioma', False),
    ('Automatic', 'Automático', 'Automatique', 'Automatisch', 'Automático', False),
    # values used everywhere
    ('On', 'Sí', 'Oui', 'Ein', 'Sim', False),
    ('Off', 'No', 'Non', 'Aus', 'Não', False),
    ('On (recommended)', 'Sí (recomendado)', 'Oui (recommandé)', 'Ein (empfohlen)', 'Sim (recomendado)', False),
    ('On (2x)', 'Sí (2x)', 'Oui (2x)', 'Ein (2x)', 'Sim (2x)', False),
    ('On (contrasting)', 'Sí (con contraste)', 'Oui (contrasté)', 'Ein (kontrastierend)', 'Sim (contrastante)', True),
    ('Hidden', 'Oculta', 'Masquée', 'Ausgeblendet', 'Oculta', True),
    ('Shown', 'Visible', 'Affichée', 'Eingeblendet', 'Visível', True),
    ('Error', 'Error', 'Erreur', 'Fehler', 'Erro', False),
    ('None', 'Ninguna', 'Aucun', 'Keine', 'Nenhuma', True),
    ('Locked', 'Bloqueadas', 'Verrouillés', 'Gesperrt', 'Bloqueadas', True),
    ('All', 'Todas', 'Tous', 'Alle', 'Todas', True),
    ('Slow', 'Lenta', 'Lente', 'Langsam', 'Lenta', False),
    ('Normal', 'Normal', 'Normal', 'Normal', 'Normal', False),
    ('Fast', 'Rápida', 'Rapide', 'Schnell', 'Rápida', False),
    ('Very fast', 'Muy rápida', 'Très rapide', 'Sehr schnell', 'Muito rápida', False),
    ('Small', 'Pequeña', 'Petite', 'Klein', 'Pequena', True),
    ('Medium', 'Mediana', 'Moyenne', 'Mittel', 'Média', True),
    ('Large', 'Grande', 'Grande', 'Groß', 'Grande', True),
    ('Extra large', 'Muy grande', 'Très grande', 'Sehr groß', 'Muito grande', True),
    ('TV mode', 'Modo TV', 'Mode TV', 'TV-Modus', 'Modo TV', False),
    ('Switch tabs', 'Cambiar de pestaña', "Changer d'onglet", 'Tabs wechseln', 'Trocar de aba', False),
    ('Back / forward', 'Atrás / adelante', 'Précédent / suivant', 'Zurück / vor', 'Voltar / avançar', False),
    ('New-tab page', 'Página de nueva pestaña', 'Page Nouvel onglet', 'Neuer-Tab-Seite', 'Página de nova aba', False),
    ('All shortcuts', 'Todos los atajos', 'Tous les raccourcis', 'Alle Tastenkürzel', 'Todos os atalhos', False),
    # Browser settings
    ('Browser settings', 'Ajustes del navegador', 'Paramètres du navigateur', 'Browser-Einstellungen', 'Configurações do navegador', False),
    ('Saved on this console', 'Se guarda en esta consola', 'Enregistré sur cette console', 'Auf dieser Konsole gespeichert', 'Salvo neste console', False),
    ('Search settings…', 'Buscar ajustes…', 'Rechercher un paramètre…', 'Einstellungen durchsuchen…', 'Pesquisar configurações…', False),
    ('Search engine', 'Motor de búsqueda', 'Moteur de recherche', 'Suchmaschine', 'Mecanismo de pesquisa', False),
    ('Home page', 'Página principal', "Page d'accueil", 'Startseite', 'Página inicial', False),
    ('Continue watching on start page', 'Seguir viendo en la página de inicio', 'Reprendre la lecture sur la page de démarrage', 'Weiterschauen auf dem Startbildschirm', 'Continuar assistindo na página de início', True),
    ('Customise start page...', 'Personalizar la página de inicio...', 'Personnaliser la page de démarrage...', 'Startbildschirm anpassen...', 'Personalizar a página de início...', True),
    ('Apps on start page...', 'Apps en la página de inicio...', 'Applis sur la page de démarrage...', 'Apps auf dem Startbildschirm...', 'Apps na página de início...', True),
    ('Default page zoom', 'Zoom predeterminado', 'Zoom par défaut', 'Standard-Seitenzoom', 'Zoom padrão da página', False),
    ('Text size', 'Tamaño del texto', 'Taille du texte', 'Textgröße', 'Tamanho do texto', False),
    ('Pointer speed', 'Velocidad del puntero', 'Vitesse du pointeur', 'Zeigergeschwindigkeit', 'Velocidade do ponteiro', False),
    ('Pointer snaps to links', 'El puntero se ajusta a los enlaces', 'Pointeur aimanté par les liens', 'Zeiger rastet an Links ein', 'Ponteiro se prende aos links', True),
    ('Pointer style', 'Estilo del puntero', 'Style du pointeur', 'Zeigerstil', 'Estilo do ponteiro', False),
    ('Pointer size', 'Tamaño del puntero', 'Taille du pointeur', 'Zeigergröße', 'Tamanho do ponteiro', False),
    ('Pointer colour', 'Color del puntero', 'Couleur du pointeur', 'Zeigerfarbe', 'Cor do ponteiro', False),
    ('Pointer outline', 'Contorno del puntero', 'Contour du pointeur', 'Zeigerumriss', 'Contorno do ponteiro', False),
    ('Pointer opacity', 'Opacidad del puntero', 'Opacité du pointeur', 'Zeigerdeckkraft', 'Opacidade do ponteiro', False),
    ('Stick dead zone', 'Zona muerta del stick', 'Zone morte du joystick', 'Stick-Totzone', 'Zona morta do analógico', False),
    ('D-pad left / right', 'Cruceta izquierda / derecha', 'Croix directionnelle gauche / droite', 'Steuerkreuz links / rechts', 'Direcional esquerda / direita', False),
    ('Dark mode', 'Modo oscuro', 'Mode sombre', 'Dunkelmodus', 'Modo escuro', False),
    ('Search suggestions', 'Sugerencias de búsqueda', 'Suggestions de recherche', 'Suchvorschläge', 'Sugestões de pesquisa', False),
    ('Tab limit', 'Límite de pestañas', "Limite d'onglets", 'Tab-Limit', 'Limite de abas', False),
    ('Tabs kept loaded', 'Pestañas que siguen cargadas', 'Onglets gardés en mémoire', 'Geladen gehaltene Tabs', 'Abas mantidas carregadas', False),
    ('Tab memory', 'Memoria de pestañas', 'Mémoire des onglets', 'Tab-Speicher', 'Memória das abas', False),
    ('Block pages from reaching the console', 'Impedir que las páginas accedan a la consola', "Empêcher les pages d'accéder à la console", 'Seiten den Zugriff auf die Konsole verwehren', 'Impedir que páginas acessem o console', False),
    ('Keyboard layout', 'Distribución del teclado', 'Disposition du clavier', 'Tastaturlayout', 'Layout do teclado', False),
    ('Word suggestions', 'Sugerencias de palabras', 'Suggestions de mots', 'Wortvorschläge', 'Sugestões de palavras', False),
    ('Learn words I type', 'Aprender las palabras que escribo', 'Apprendre les mots que je tape', 'Eingegebene Wörter lernen', 'Aprender as palavras que eu digito', False),
    ('Clear learned words', 'Borrar palabras aprendidas', 'Effacer les mots appris', 'Gelernte Wörter löschen', 'Limpar palavras aprendidas', False),
    ('Web pages can use the controller', 'Las páginas web pueden usar el mando', 'Les pages web peuvent utiliser la manette', 'Webseiten dürfen den Controller nutzen', 'Páginas da web podem usar o controle', False),
    ('Autoplay', 'Reproducción automática', 'Lecture automatique', 'Automatische Wiedergabe', 'Reprodução automática', False),
    ('Captions', 'Subtítulos', 'Sous-titres', 'Untertitel', 'Legendas', False),
    ('HTTPS-only mode', 'Modo solo HTTPS', 'Mode HTTPS uniquement', 'Nur-HTTPS-Modus', 'Modo somente HTTPS', False),
    ('Ask sites not to sell or share my data', 'Pedir a los sitios que no vendan ni compartan mis datos', 'Demander aux sites de ne pas vendre ni partager mes données', 'Websites bitten, meine Daten nicht zu verkaufen oder weiterzugeben', 'Pedir aos sites que não vendam nem compartilhem meus dados', False),
    ('Keep history', 'Conservar el historial', "Conserver l'historique", 'Verlauf behalten', 'Manter histórico', False),
    ('Reload pages when back online', 'Recargar páginas al recuperar la conexión', 'Recharger les pages au retour de la connexion', 'Seiten neu laden, wenn wieder online', 'Recarregar páginas quando a conexão voltar', False),
    ('Tell sites this is Omni', 'Indicar a los sitios que es Omni', "Indiquer aux sites qu'il s'agit d'Omni", 'Websites mitteilen, dass dies Omni ist', 'Informar aos sites que este é o Omni', False),
    ('JavaScript JIT (faster pages)', 'JIT de JavaScript (páginas más rápidas)', 'JIT JavaScript (pages plus rapides)', 'JavaScript-JIT (schnellere Seiten)', 'JIT do JavaScript (páginas mais rápidas)', False),
    ('Quick bar and apps...', 'Barra rápida y apps...', 'Barre rapide et applis...', 'Schnellleiste und Apps...', 'Barra rápida e apps...', False),
    ('Quick access buttons...', 'Botones de acceso rápido...', "Boutons d'accès rapide...", 'Schnellzugriffstasten...', 'Botões de acesso rápido...', False),
    ('Quick access buttons', 'Botones de acceso rápido', "Boutons d'accès rapide", 'Schnellzugriffstasten', 'Botões de acesso rápido', False),
    ('Quick access row', 'Fila de acceso rápido', "Rangée d'accès rapide", 'Schnellzugriffsleiste', 'Linha de acesso rápido', False),
    ('Bottom button bar', 'Barra de botones inferior', 'Barre de boutons inférieure', 'Untere Tastenleiste', 'Barra de botões inferior', False),
    ('Night light', 'Luz nocturna', 'Éclairage nocturne', 'Nachtlicht', 'Luz noturna', False),
    ('Night light warmth', 'Calidez de la luz nocturna', "Chaleur de l'éclairage nocturne", 'Nachtlicht-Wärme', 'Tom da luz noturna', True),
    ('Night light from', 'Luz nocturna desde', 'Éclairage nocturne à partir de', 'Nachtlicht ab', 'Luz noturna a partir de', False),
    ('Night light until', 'Luz nocturna hasta', "Éclairage nocturne jusqu'à", 'Nachtlicht bis', 'Luz noturna até', False),
    ('Show controls guide', 'Mostrar guía de controles', 'Afficher le guide des commandes', 'Steuerungsübersicht anzeigen', 'Mostrar guia de controles', False),
    ('High contrast', 'Alto contraste', 'Contraste élevé', 'Hoher Kontrast', 'Alto contraste', False),
    ('Large pointer', 'Puntero grande', 'Grand pointeur', 'Großer Zeiger', 'Ponteiro grande', False),
    ('Controller, theme and display...', 'Mando, tema y pantalla...', 'Manette, thème et affichage...', 'Controller, Design und Anzeige...', 'Controle, tema e tela...', False),
    ('Send links from your phone', 'Enviar enlaces desde el móvil', 'Envoyer des liens depuis votre téléphone', 'Links vom Smartphone senden', 'Enviar links do celular', False),
    ('Passwords', 'Contraseñas', 'Mots de passe', 'Passwörter', 'Senhas', False),
    ('Autofill', 'Autocompletar', 'Saisie automatique', 'Automatisch ausfüllen', 'Preenchimento automático', False),
    ('Site permissions', 'Permisos de sitios', 'Autorisations des sites', 'Website-Berechtigungen', 'Permissões de sites', False),
    ('Sites with custom settings', 'Sitios con ajustes personalizados', 'Sites avec paramètres personnalisés', 'Websites mit eigenen Einstellungen', 'Sites com configurações personalizadas', False),
    ('About Omni', 'Acerca de Omni', "À propos d'Omni", 'Über Omni', 'Sobre o Omni', False),
    # settings search sections (dim prefix of found rows)
    ('General', 'General', 'Général', 'Allgemein', 'Geral', False),
    ('Keyboard', 'Teclado', 'Clavier', 'Tastatur', 'Teclado', False),
    ('Privacy', 'Privacidad', 'Confidentialité', 'Datenschutz', 'Privacidade', False),
    ('Media', 'Multimedia', 'Médias', 'Medien', 'Mídia', False),
    ('Display', 'Pantalla', 'Affichage', 'Anzeige', 'Tela', False),
    ('Network', 'Red', 'Réseau', 'Netzwerk', 'Rede', False),
    ('Browsing', 'Navegación', 'Navigation', 'Surfen', 'Navegação', False),
    # Options (quick menu) and page menu
    ('Options', 'Opciones', 'Options', 'Optionen', 'Opções', False),
    ('Browse, adjust, open an app', 'Navega, ajusta o abre una app', 'Naviguer, régler, ouvrir une appli', 'Surfen, anpassen, App öffnen', 'Navegue, ajuste ou abra um app', False),
    ('Browse', 'Navegar', 'Naviguer', 'Surfen', 'Navegar', False),
    ('Quick toggles', 'Ajustes rápidos', 'Réglages rapides', 'Schnelleinstellungen', 'Ajustes rápidos', False),
    ('More', 'Más', 'Plus', 'Mehr', 'Mais', False),
    ('Settings', 'Ajustes', 'Paramètres', 'Einstellungen', 'Configurações', False),
    ('Forward', 'Adelante', 'Suivant', 'Vorwärts', 'Avançar', False),
    ('Stop', 'Detener', 'Arrêter', 'Stopp', 'Parar', False),
    ('Reload', 'Recargar', 'Actualiser', 'Neu laden', 'Recarregar', False),
    ('Reload page', 'Recargar página', 'Actualiser la page', 'Seite neu laden', 'Recarregar página', False),
    ('Home', 'Inicio', 'Accueil', 'Startseite', 'Início', False),
    ('Find on page', 'Buscar en la página', 'Rechercher dans la page', 'Auf Seite suchen', 'Localizar na página', False),
    ('Zoom out', 'Alejar', 'Zoom arrière', 'Verkleinern', 'Diminuir zoom', False),
    ('Zoom in', 'Acercar', 'Zoom avant', 'Vergrößern', 'Aumentar zoom', False),
    ('Reset zoom', 'Restablecer zoom', 'Réinitialiser le zoom', 'Zoom zurücksetzen', 'Redefinir zoom', False),
    ('Reader view', 'Vista de lectura', 'Mode lecture', 'Leseansicht', 'Modo leitura', False),
    ('Show original', 'Mostrar original', "Afficher l'original", 'Original anzeigen', 'Mostrar original', False),
    ('Translate', 'Traducir', 'Traduire', 'Übersetzen', 'Traduzir', False),
    ('Translate page', 'Traducir página', 'Traduire la page', 'Seite übersetzen', 'Traduzir página', False),
    ('Remove bookmark', 'Quitar marcador', 'Supprimer le favori', 'Lesezeichen entfernen', 'Remover favorito', False),
    ('Bookmark page', 'Añadir a marcadores', 'Ajouter aux favoris', 'Lesezeichen setzen', 'Adicionar aos favoritos', False),
    ('Copy address', 'Copiar dirección', "Copier l'adresse", 'Adresse kopieren', 'Copiar endereço', False),
    ('Copy page address', 'Copiar dirección de la página', "Copier l'adresse de la page", 'Seitenadresse kopieren', 'Copiar endereço da página', False),
    ('Site settings', 'Ajustes del sitio', 'Paramètres du site', 'Website-Einstellungen', 'Configurações do site', False),
    ('Bookmarks', 'Marcadores', 'Favoris', 'Lesezeichen', 'Favoritos', False),
    ('History', 'Historial', 'Historique', 'Verlauf', 'Histórico', False),
    ('Downloads', None, None, None, None, False),   # R2 glossary: the Downloads app's name stays English
    ('Screenshots', 'Capturas', "Captures d'écran", 'Screenshots', 'Capturas de tela', False),
    ('Apps', 'Apps', 'Applis', 'Apps', 'Apps', False),
    ('Reopen closed tab', 'Reabrir pestaña cerrada', "Rouvrir l'onglet fermé", 'Geschlossenen Tab wieder öffnen', 'Reabrir aba fechada', False),
    ('New private tab', 'Nueva pestaña privada', 'Nouvel onglet privé', 'Neuer privater Tab', 'Nova aba privada', False),
    ('Sleep timer', 'Temporizador de apagado', 'Minuterie de veille', 'Einschlaftimer', 'Timer de desligamento', True),
    ('Browser tools', 'Herramientas del navegador', 'Outils du navigateur', 'Browser-Werkzeuge', 'Ferramentas do navegador', False),
    ('Controls', 'Controles', 'Commandes', 'Steuerung', 'Controles', False),
    ('Exit Omni', 'Salir de Omni', 'Quitter Omni', 'Omni beenden', 'Sair do Omni', False),
    ('No site open', 'Ningún sitio abierto', 'Aucun site ouvert', 'Keine Website geöffnet', 'Nenhum site aberto', False),
    ('uBlock on this site', 'uBlock en este sitio', 'uBlock sur ce site', 'uBlock auf dieser Website', 'uBlock neste site', False),
    ('uBlock on all sites', 'uBlock en todos los sitios', 'uBlock sur tous les sites', 'uBlock auf allen Websites', 'uBlock em todos os sites', False),
    ('Off everywhere', 'No (en ningún sitio)', 'Non (nulle part)', 'Aus (überall)', 'Não (em nenhum site)', True),
    ('Off (allowed)', 'No (permitido)', 'Non (autorisé)', 'Aus (erlaubt)', 'Não (permitido)', True),
    ('Site version', 'Versión del sitio', 'Version du site', 'Website-Version', 'Versão do site', False),
    ('Mobile (iPhone)', 'Móvil (iPhone)', 'Mobile (iPhone)', 'Mobil (iPhone)', 'Celular (iPhone)', False),
    ('Desktop', 'Escritorio', 'Ordinateur', 'Desktop', 'Computador', False),
    ('Zoom for this site', 'Zoom para este sitio', 'Zoom pour ce site', 'Zoom für diese Website', 'Zoom para este site', False),
    ('Open in background tab', 'Abrir en pestaña en segundo plano', 'Ouvrir dans un onglet en arrière-plan', 'In Hintergrund-Tab öffnen', 'Abrir em aba em segundo plano', False),
    ('Open link in new tab', 'Abrir enlace en una pestaña nueva', 'Ouvrir le lien dans un nouvel onglet', 'Link in neuem Tab öffnen', 'Abrir link em nova aba', False),
    ('Open in private tab', 'Abrir en pestaña privada', 'Ouvrir dans un onglet privé', 'In privatem Tab öffnen', 'Abrir em aba privada', False),
    ('Copy link address', 'Copiar dirección del enlace', "Copier l'adresse du lien", 'Linkadresse kopieren', 'Copiar endereço do link', False),
    ('Save link target', 'Guardar destino del enlace', 'Enregistrer la cible du lien', 'Linkziel speichern', 'Salvar destino do link', False),
    ('Add link to shortcuts', 'Añadir enlace a accesos directos', 'Ajouter le lien aux raccourcis', 'Link zu Verknüpfungen hinzufügen', 'Adicionar link aos atalhos', False),
    ('Bookmark link', 'Añadir enlace a marcadores', 'Ajouter le lien aux favoris', 'Link als Lesezeichen speichern', 'Adicionar link aos favoritos', False),
    ('Open image in new tab', 'Abrir imagen en una pestaña nueva', "Ouvrir l'image dans un nouvel onglet", 'Bild in neuem Tab öffnen', 'Abrir imagem em nova aba', False),
    ('Copy image address', 'Copiar dirección de la imagen', "Copier l'adresse de l'image", 'Bildadresse kopieren', 'Copiar endereço da imagem', False),
    ('Save image', 'Guardar imagen', "Enregistrer l'image", 'Bild speichern', 'Salvar imagem', False),
    ('Open video in new tab', 'Abrir vídeo en una pestaña nueva', 'Ouvrir la vidéo dans un nouvel onglet', 'Video in neuem Tab öffnen', 'Abrir vídeo em nova aba', False),
    # panel titles
    ('Tabs', 'Pestañas', 'Onglets', 'Tabs', 'Abas', False),
    ('Clear browsing data', 'Borrar datos de navegación', 'Effacer les données de navigation', 'Browserdaten löschen', 'Limpar dados de navegação', False),
    ('Reading list', 'Lista de lectura', 'Liste de lecture', 'Leseliste', 'Lista de leitura', False),
    ('Now playing', 'Reproduciendo', 'En cours de lecture', 'Wird abgespielt', 'Tocando agora', False),
    ('Nothing is playing', 'No se reproduce nada', 'Aucune lecture en cours', 'Es wird nichts abgespielt', 'Nada está tocando', False),
    ('Saved logins on this console', 'Inicios de sesión guardados en esta consola', 'Identifiants enregistrés sur cette console', 'Auf dieser Konsole gespeicherte Anmeldungen', 'Logins salvos neste console', False),
    ('Sessions', 'Sesiones', 'Sessions', 'Sitzungen', 'Sessões', False),
    ('Add-ons', 'Complementos', 'Modules complémentaires', 'Add-ons', 'Complementos', False),
    ('Customise start page', 'Personalizar la página de inicio', 'Personnaliser la page de démarrage', 'Startbildschirm anpassen', 'Personalizar a página de início', True),
    ('Apps on start page', 'Apps en la página de inicio', 'Applis sur la page de démarrage', 'Apps auf dem Startbildschirm', 'Apps na página de início', True),
    ('Tab group', 'Grupo de pestañas', "Groupe d'onglets", 'Tab-Gruppe', 'Grupo de abas', False),
    ('Edit bookmark', 'Editar marcador', 'Modifier le favori', 'Lesezeichen bearbeiten', 'Editar favorito', False),
    ('Move to folder', 'Mover a carpeta', 'Déplacer vers un dossier', 'In Ordner verschieben', 'Mover para pasta', False),
    ('Blocked pop-ups', 'Ventanas emergentes bloqueadas', 'Pop-ups bloqués', 'Blockierte Pop-ups', 'Pop-ups bloqueados', False),
    ('Not secure', 'No seguro', 'Non sécurisé', 'Nicht sicher', 'Não seguro', False),
    ('Load failed', 'Error al cargar', 'Échec du chargement', 'Laden fehlgeschlagen', 'Falha ao carregar', False),
    ('Page tweaks', 'Ajustes de página', 'Retouches de page', 'Seitenanpassungen', 'Ajustes de página', True),
    # hint bar
    ('Back', 'Atrás', 'Retour', 'Zurück', 'Voltar', False),
    ('Choose', 'Elegir', 'Choisir', 'Auswählen', 'Escolher', False),
    ('Change', 'Cambiar', 'Modifier', 'Ändern', 'Alterar', False),
    ('Open', 'Abrir', 'Ouvrir', 'Öffnen', 'Abrir', False),
    ('Delete', 'Eliminar', 'Supprimer', 'Löschen', 'Excluir', False),
    ('Close', 'Cerrar', 'Fermer', 'Schließen', 'Fechar', False),
    ('Cancel', 'Cancelar', 'Annuler', 'Abbrechen', 'Cancelar', False),
    ('Switch', 'Cambiar', 'Basculer', 'Wechseln', 'Alternar', False),
    ('Edit', 'Editar', 'Modifier', 'Bearbeiten', 'Editar', False),
    ('Close tab', 'Cerrar pestaña', "Fermer l'onglet", 'Tab schließen', 'Fechar aba', False),
    ('Search', 'Buscar', 'Rechercher', 'Suchen', 'Pesquisar', False),
    ('View', 'Ver', 'Afficher', 'Ansehen', 'Ver', False),
    ('Rename', 'Cambiar nombre', 'Renommer', 'Umbenennen', 'Renomear', False),
    ('Move up', 'Subir', 'Monter', 'Nach oben', 'Mover para cima', False),
    ('Move down', 'Bajar', 'Descendre', 'Nach unten', 'Mover para baixo', False),
    ('Click', 'Clic', 'Cliquer', 'Klicken', 'Clicar', False),
    ('Address', 'Dirección', 'Adresse', 'Adresse', 'Endereço', False),
    ('New tab', 'Nueva pestaña', 'Nouvel onglet', 'Neuer Tab', 'Nova aba', False),
    ('Menu', 'Menú', 'Menu', 'Menü', 'Menu', False),
    ('Choose setting', 'Elegir ajuste', 'Choisir un réglage', 'Einstellung wählen', 'Escolher configuração', False),
    ('Done', 'Listo', 'Terminé', 'Fertig', 'Concluído', False),
    ('Clear', 'Borrar', 'Effacer', 'Löschen', 'Limpar', False),
    ('Reset', 'Restablecer', 'Réinitialiser', 'Zurücksetzen', 'Redefinir', False),
    ('Remove', 'Quitar', 'Retirer', 'Entfernen', 'Remover', False),
    ('Not now', 'Ahora no', 'Pas maintenant', 'Nicht jetzt', 'Agora não', False),
    ('Forget', 'Olvidar', 'Oublier', 'Vergessen', 'Esquecer', False),
    ('Actions', 'Acciones', 'Actions', 'Aktionen', 'Ações', False),
    ('Reset this site', 'Restablecer este sitio', 'Réinitialiser ce site', 'Diese Website zurücksetzen', 'Redefinir este site', False),
    ('Keep loaded', 'Mantener cargada', 'Garder en mémoire', 'Geladen lassen', 'Manter carregada', True),
    ('Unload', 'Liberar', 'Décharger', 'Entladen', 'Liberar', True),
    ('D-pad ◀ ▶ change', 'Cruceta ◀ ▶ cambiar', 'Croix ◀ ▶ modifier', 'Steuerkreuz ◀ ▶ ändern', 'Direcional ◀ ▶ alterar', False),
    ('D-pad ◀ ▶ change   Y reset', 'Cruceta ◀ ▶ cambiar   Y restablecer', 'Croix ◀ ▶ modifier   Y réinitialiser', 'Steuerkreuz ◀ ▶ ändern   Y zurücksetzen', 'Direcional ◀ ▶ alterar   Y redefinir', False),
    ('D-pad ◀ ▶ change   Y reset   Home page: X current page', 'Cruceta ◀ ▶ cambiar   Y restablecer   Página principal: X página actual', "Croix ◀ ▶ modifier   Y réinitialiser   Page d'accueil : X page actuelle", 'Steuerkreuz ◀ ▶ ändern   Y zurücksetzen   Startseite: X aktuelle Seite', 'Direcional ◀ ▶ alterar   Y redefinir   Página inicial: X página atual', False),
    ('D-pad: move   L1/R1: page', 'Cruceta: mover   L1/R1: página', 'Croix : déplacer   L1/R1 : page', 'Steuerkreuz: bewegen   L1/R1: Seite', 'Direcional: mover   L1/R1: página', False),
    ('D-pad: choose   Right stick: scroll', 'Cruceta: elegir   Stick derecho: desplazar', 'Croix : choisir   Joystick droit : défiler', 'Steuerkreuz: wählen   Rechter Stick: scrollen', 'Direcional: escolher   Analógico direito: rolar', False),
    ('Applies at once, no reload', 'Se aplica al instante, sin recargar', "S'applique tout de suite, sans rechargement", 'Wirkt sofort, ohne Neuladen', 'Aplica na hora, sem recarregar', False),
    # notices (toast)
    ('Open a web page first', 'Abre primero una página web', "Ouvrez d'abord une page web", 'Öffne zuerst eine Webseite', 'Abra uma página da web primeiro', False),
    ('Open a website first', 'Abre primero un sitio web', "Ouvrez d'abord un site web", 'Öffne zuerst eine Website', 'Abra um site primeiro', False),
    ('That tab is closed', 'Esa pestaña está cerrada', 'Cet onglet est fermé', 'Dieser Tab ist geschlossen', 'Essa aba está fechada', False),
    ('Nothing to copy', 'Nada que copiar', 'Rien à copier', 'Nichts zu kopieren', 'Nada para copiar', False),
    ('Nothing copied yet', 'Aún no se ha copiado nada', "Rien n'a encore été copié", 'Noch nichts kopiert', 'Nada copiado ainda', False),
    ('Nothing to undo', 'Nada que deshacer', 'Rien à annuler', 'Nichts rückgängig zu machen', 'Nada para desfazer', False),
    ('Pasted', 'Pegado', 'Collé', 'Eingefügt', 'Colado', False),
    ('Login deleted', 'Inicio de sesión eliminado', 'Identifiant supprimé', 'Anmeldung gelöscht', 'Login excluído', False),
    ('Already bookmarked', 'Ya está en marcadores', 'Déjà dans les favoris', 'Bereits ein Lesezeichen', 'Já está nos favoritos', False),
    ('No page to bookmark', 'No hay ninguna página para añadir a marcadores', 'Aucune page à ajouter aux favoris', 'Keine Seite für ein Lesezeichen', 'Nenhuma página para adicionar aos favoritos', False),
    ('Only web pages can be bookmarked', 'Solo se pueden guardar páginas web en marcadores', 'Seules les pages web peuvent être ajoutées aux favoris', 'Nur Webseiten können Lesezeichen werden', 'Só páginas da web podem ir para os favoritos', False),
    ('Already in shortcuts', 'Ya está en accesos directos', 'Déjà dans les raccourcis', 'Bereits in den Verknüpfungen', 'Já está nos atalhos', False),
    ("Couldn't save shortcuts", 'No se pudieron guardar los accesos directos', "Impossible d'enregistrer les raccourcis", 'Verknüpfungen konnten nicht gespeichert werden', 'Não foi possível salvar os atalhos', False),
    ('A folder needs a name', 'La carpeta necesita un nombre', 'Le dossier doit avoir un nom', 'Der Ordner braucht einen Namen', 'A pasta precisa de um nome', False),
    ('Bookmarks are full (500): delete some first', 'Los marcadores están llenos (500): elimina algunos primero', 'Les favoris sont pleins (500) : supprimez-en d\'abord', 'Lesezeichen sind voll (500): zuerst einige löschen', 'Os favoritos estão cheios (500): exclua alguns primeiro', False),
    ("This page can't be translated", 'Esta página no se puede traducir', 'Cette page ne peut pas être traduite', 'Diese Seite kann nicht übersetzt werden', 'Esta página não pode ser traduzida', False),
    ('Translating with Google Translate...', 'Traduciendo con Google Traductor...', 'Traduction avec Google Traduction...', 'Übersetzen mit Google Übersetzer...', 'Traduzindo com o Google Tradutor...', False),
    ('Browsing data cleared', 'Datos de navegación borrados', 'Données de navigation effacées', 'Browserdaten gelöscht', 'Dados de navegação limpos', False),
    ('Clearing browsing data...', 'Borrando datos de navegación...', 'Effacement des données de navigation...', 'Browserdaten werden gelöscht...', 'Limpando dados de navegação...', False),
    ('Reader view works on web pages', 'La vista de lectura funciona en páginas web', 'Le mode lecture fonctionne sur les pages web', 'Die Leseansicht funktioniert auf Webseiten', 'O modo leitura funciona em páginas da web', False),
    ('Reader view...', 'Vista de lectura...', 'Mode lecture...', 'Leseansicht...', 'Modo leitura...', False),
    ('Reader view: no article found on this page', 'Vista de lectura: no hay ningún artículo en esta página', 'Mode lecture : aucun article trouvé sur cette page', 'Leseansicht: kein Artikel auf dieser Seite gefunden', 'Modo leitura: nenhum artigo encontrado nesta página', False),
    ('History is empty', 'El historial está vacío', "L'historique est vide", 'Der Verlauf ist leer', 'O histórico está vazio', False),
    ('Removed from history', 'Eliminado del historial', "Supprimé de l'historique", 'Aus dem Verlauf entfernt', 'Removido do histórico', False),
    ('Sent to Downloads', 'Enviado a Downloads', 'Envoyé dans Downloads', 'An Downloads gesendet', 'Enviado para Downloads', False),
    ('Zoom works on web pages', 'El zoom funciona en páginas web', 'Le zoom fonctionne sur les pages web', 'Zoom funktioniert auf Webseiten', 'O zoom funciona em páginas da web', False),
    ('Home: the new-tab page', 'Página principal: la de nueva pestaña', "Page d'accueil : la page Nouvel onglet", 'Startseite: die Neuer-Tab-Seite', 'Página inicial: a página de nova aba', False),
    ('Stopped', 'Detenido', 'Arrêté', 'Gestoppt', 'Parado', False),
    ('Reloading...', 'Recargando...', 'Actualisation...', 'Wird neu geladen...', 'Recarregando...', False),
    ('Screenshots are off in private tabs', 'Las capturas están desactivadas en pestañas privadas', "Les captures d'écran sont désactivées dans les onglets privés", 'Screenshots sind in privaten Tabs aus', 'Capturas de tela ficam desativadas em abas privadas', False),
    ('Saving screenshot...', 'Guardando captura...', "Enregistrement de la capture d'écran...", 'Screenshot wird gespeichert...', 'Salvando captura de tela...', False),
    ('Learned words cleared', 'Palabras aprendidas borradas', 'Mots appris effacés', 'Gelernte Wörter gelöscht', 'Palavras aprendidas limpas', False),
    ('Private tab: no history; cookies and site data are forgotten when Omni closes', 'Pestaña privada: sin historial; las cookies y los datos de sitios se olvidan al cerrar Omni', "Onglet privé : pas d'historique ; les cookies et données de site sont oubliés à la fermeture d'Omni", 'Privater Tab: kein Verlauf; Cookies und Websitedaten werden beim Schließen von Omni vergessen', 'Aba privada: sem histórico; cookies e dados de sites são esquecidos quando o Omni fecha', False),
    ("The page isn't ready yet", 'La página aún no está lista', "La page n'est pas encore prête", 'Die Seite ist noch nicht bereit', 'A página ainda não está pronta', False),
    ('Unlocking...', 'Desbloqueando...', 'Déverrouillage...', 'Wird entsperrt...', 'Desbloqueando...', False),
    ('Quick access: default buttons', 'Acceso rápido: botones predeterminados', 'Accès rapide : boutons par défaut', 'Schnellzugriff: Standardtasten', 'Acesso rápido: botões padrão', False),
    ('Quick access is full: remove a button first', 'El acceso rápido está lleno: quita primero un botón', "L'accès rapide est plein : retirez d'abord un bouton", 'Schnellzugriff ist voll: zuerst eine Taste entfernen', 'O acesso rápido está cheio: remova um botão primeiro', False),
    ('Sleep timer: paused playback', 'Temporizador: reproducción en pausa', 'Minuterie : lecture mise en pause', 'Einschlaftimer: Wiedergabe pausiert', 'Timer: reprodução pausada', True),
    ('Sleep timer: pausing playback in 1 minute', 'Temporizador: la reproducción se pausará en 1 minuto', 'Minuterie : pause de la lecture dans 1 minute', 'Einschlaftimer: Wiedergabe pausiert in 1 Minute', 'Timer: a reprodução será pausada em 1 minuto', True),
    ('Captions: back to the default look', 'Subtítulos: aspecto predeterminado restaurado', 'Sous-titres : apparence par défaut rétablie', 'Untertitel: Standarddarstellung wiederhergestellt', 'Legendas: aparência padrão restaurada', False),
    ('Autofill profile cleared', 'Perfil de autocompletar borrado', 'Profil de saisie automatique effacé', 'Profil für automatisches Ausfüllen gelöscht', 'Perfil de preenchimento automático limpo', False),
    # prefix entries (the rest - a name, address or host - is kept as it is)
    ('Sent to Downloads: *', 'Enviado a Downloads: *', 'Envoyé dans Downloads : *', 'An Downloads gesendet: *', 'Enviado para Downloads: *', False),
    ('Saved to shortcuts: *', 'Guardado en accesos directos: *', 'Ajouté aux raccourcis : *', 'Zu Verknüpfungen hinzugefügt: *', 'Salvo nos atalhos: *', False),
    ('Already in shortcuts: *', 'Ya está en accesos directos: *', 'Déjà dans les raccourcis : *', 'Bereits in Verknüpfungen: *', 'Já está nos atalhos: *', False),
    ('Removed from shortcuts: *', 'Quitado de accesos directos: *', 'Retiré des raccourcis : *', 'Aus Verknüpfungen entfernt: *', 'Removido dos atalhos: *', False),
    ('Removed: *', 'Eliminado: *', 'Supprimé : *', 'Entfernt: *', 'Removido: *', False),
    ('Bookmarked: *', 'Añadido a marcadores: *', 'Ajouté aux favoris : *', 'Lesezeichen gesetzt: *', 'Adicionado aos favoritos: *', False),
    ('Bookmark removed: *', 'Marcador eliminado: *', 'Favori supprimé : *', 'Lesezeichen entfernt: *', 'Favorito removido: *', False),
    ('Saved for later: *', 'Guardado para después: *', 'Enregistré pour plus tard : *', 'Für später gespeichert: *', 'Salvo para depois: *', False),
    ('Download failed: *', 'Error en la descarga: *', 'Échec du téléchargement : *', 'Download fehlgeschlagen: *', 'Falha no download: *', False),
    ('Permissions reset for *', 'Permisos restablecidos para *', 'Autorisations réinitialisées pour *', 'Berechtigungen zurückgesetzt für *', 'Permissões redefinidas para *', False),
    ('Home page set to *', 'Página principal: *', "Page d'accueil : *", 'Startseite: *', 'Página inicial: *', False),
    ('Login saved for *', 'Inicio de sesión guardado para *', 'Identifiant enregistré pour *', 'Anmeldung gespeichert für *', 'Login salvo para *', False),
    ('uBlock is off for *', 'uBlock está desactivado en *', 'uBlock est désactivé pour *', 'uBlock ist aus für *', 'uBlock está desativado em *', False),
    ('Opened a link sent from *', 'Enlace abierto, enviado desde *', 'Lien ouvert, envoyé depuis *', 'Link geöffnet, gesendet von *', 'Link aberto, enviado de *', False),
    ("Couldn't save this page: *", 'No se pudo guardar esta página: *', "Impossible d'enregistrer cette page : *", 'Diese Seite konnte nicht gespeichert werden: *', 'Não foi possível salvar esta página: *', False),
]

# ---------------------------------------------------------------------------------------------------------------
# OMNI_UI_LANG_V1_R2: stage 2 strings (glossary: see the docstring). Same columns. A row whose four translations are
# None is English-only on purpose (a name): it is listed so the table says so, and it is never loaded.
# Controller button names stay English in prose (the guide's {Cross} tokens expand to the English names).
# ---------------------------------------------------------------------------------------------------------------
T2 = [
    # English-only (names)
    ('uBlock', None, None, None, None, False),
    ('YouTube', None, None, None, None, False),
    ('PlayStation', None, None, None, None, False),
    ('Xbox', None, None, None, None, False),
    ('Touchpad', None, None, None, None, False),
    ('OK', None, None, None, None, False),
    # --- Controls guide (OmniControlsHelp.h): sections, where-lines, actions, notes ---------------------------------
    ('Video', 'Vídeo', 'Vidéo', 'Video', 'Vídeo', False),
    ('Quick actions', 'Acciones rápidas', 'Actions rapides', 'Schnellaktionen', 'Ações rápidas', False),
    ('A web page, no panel open', 'Una página web, sin paneles abiertos', 'Une page web, aucun panneau ouvert', 'Eine Webseite, kein Bereich offen', 'Uma página da web, sem painel aberto', False),
    ('Address bar and text boxes', 'Barra de direcciones y cuadros de texto', "Barre d'adresse et champs de texte", 'Adressleiste und Textfelder', 'Barra de endereço e caixas de texto', False),
    ('Options > Browse > Tabs', 'Opciones > Navegar > Pestañas', 'Options > Naviguer > Onglets', 'Optionen > Surfen > Tabs', 'Opções > Navegar > Abas', False),
    ('Full-screen video, Now playing', 'Vídeo a pantalla completa, Reproduciendo', 'Vidéo en plein écran, En cours de lecture', 'Vollbildvideo, Wird abgespielt', 'Vídeo em tela cheia, Tocando agora', False),
    ('Over a web page', 'Sobre una página web', 'Sur une page web', 'Über einer Webseite', 'Sobre uma página da web', False),
    ('Options > Browse > Reading list', 'Opciones > Navegar > Lista de lectura', 'Options > Naviguer > Liste de lecture', 'Optionen > Surfen > Leseliste', 'Opções > Navegar > Lista de leitura', False),
    ('Options > More > Downloads', 'Opciones > Más > Downloads', 'Options > Plus > Downloads', 'Optionen > Mehr > Downloads', 'Opções > Mais > Downloads', False),
    ('Options > Browse > History', 'Opciones > Navegar > Historial', 'Options > Naviguer > Historique', 'Optionen > Surfen > Verlauf', 'Opções > Navegar > Histórico', False),
    ('Hold', 'Mantener', 'Maintenir', 'Halten', 'Segurar', False),
    ('Section', 'Sección', 'Section', 'Bereich', 'Seção', False),
    ('Page %d of %d   D-pad ▲ ▼ more', 'Página %d de %d   Cruceta ▲ ▼ más', 'Page %d sur %d   Croix ▲ ▼ suite', 'Seite %d von %d   Steuerkreuz ▲ ▼ mehr', 'Página %d de %d   Direcional ▲ ▼ mais', False),
    ('Press Options → Controls for all shortcuts', 'Pulsa Options → Controles para ver todos los atajos', 'Appuyez sur Options → Commandes pour tous les raccourcis', 'Drücke Options → Steuerung für alle Tastenkürzel', 'Pressione Options → Controles para ver todos os atalhos', False),
    ('Press Menu → Controls for all shortcuts', 'Pulsa Menu → Controles para ver todos los atajos', 'Appuyez sur Menu → Commandes pour tous les raccourcis', 'Drücke Menu → Steuerung für alle Tastenkürzel', 'Pressione Menu → Controles para ver todos os atalhos', False),
    ('Address bar', 'Barra de direcciones', "Barre d'adresse", 'Adressleiste', 'Barra de endereço', False),
    ("In a page's text box: type there", 'En un cuadro de texto de la página: escribir en él', 'Dans un champ de texte de la page : y écrire', 'Im Textfeld einer Seite: dort schreiben', 'Em uma caixa de texto da página: digitar nela', False),
    ('Previous / next tab', 'Pestaña anterior / siguiente', 'Onglet précédent / suivant', 'Vorheriger / nächster Tab', 'Aba anterior / próxima', False),
    ('A pinned tab asks first', 'Una pestaña fijada pregunta antes', "Un onglet épinglé demande d'abord", 'Ein angehefteter Tab fragt vorher', 'Uma aba fixada pergunta antes', False),
    ('Add this page to shortcuts', 'Añadir esta página a accesos directos', 'Ajouter cette page aux raccourcis', 'Diese Seite zu den Verknüpfungen hinzufügen', 'Adicionar esta página aos atalhos', False),
    ('Unless an add-on quick switch uses {L3}', 'Salvo que el cambio rápido de un complemento use {L3}', "Sauf si le bouton rapide d'un module utilise {L3}", 'Außer ein Add-on-Schnellschalter nutzt {L3}', 'A menos que o atalho rápido de um complemento use {L3}', True),
    ('Unless an add-on quick switch uses the touchpad', 'Salvo que el cambio rápido de un complemento use el panel táctil', "Sauf si le bouton rapide d'un module utilise le pavé tactile", 'Außer ein Add-on-Schnellschalter nutzt das Touchpad', 'A menos que o atalho rápido de um complemento use o touchpad', True),
    ('Browser settings > D-pad left / right can switch tabs', 'Ajustes del navegador > Cruceta izquierda / derecha puede cambiar de pestaña', "Paramètres du navigateur > Croix directionnelle gauche / droite peut changer d'onglet", 'Browser-Einstellungen > Steuerkreuz links / rechts kann Tabs wechseln', 'Configurações do navegador > Direcional esquerda / direita pode trocar de aba', False),
    ('Scroll', 'Desplazar', 'Défiler', 'Scrollen', 'Rolar', False),
    ('Move the pointer', 'Mover el puntero', 'Déplacer le pointeur', 'Zeiger bewegen', 'Mover o ponteiro', False),
    ('Scroll in any direction', 'Desplazar en cualquier dirección', 'Défiler dans toutes les directions', 'In jede Richtung scrollen', 'Rolar em qualquer direção', False),
    ('Options menu', 'Menú Opciones', 'Menu Options', 'Optionsmenü', 'Menu Opções', False),
    ('{Options} again closes it', '{Options} otra vez lo cierra', '{Options} à nouveau le ferme', 'Erneut {Options} schließt es', '{Options} de novo fecha o menu', False),
    ('Find bar: previous / next match', 'Barra de búsqueda: coincidencia anterior / siguiente', 'Barre de recherche : résultat précédent / suivant', 'Suchleiste: vorheriger / nächster Treffer', 'Barra de localizar: resultado anterior / próximo', False),
    ('D-pad left / right too', 'También cruceta izquierda / derecha', 'Croix gauche / droite aussi', 'Auch Steuerkreuz links / rechts', 'Direcional esquerda / direita também', False),
    ('Find bar: search for something else', 'Barra de búsqueda: buscar otra cosa', 'Barre de recherche : chercher autre chose', 'Suchleiste: nach etwas anderem suchen', 'Barra de localizar: procurar outra coisa', False),
    ('Options > More > Find on page opens the bar', 'Opciones > Más > Buscar en la página abre la barra', 'Options > Plus > Rechercher dans la page ouvre la barre', 'Optionen > Mehr > Auf Seite suchen öffnet die Leiste', 'Opções > Mais > Localizar na página abre a barra', False),
    ('Find bar: Match case on / off', 'Barra de búsqueda: distinguir mayúsculas sí / no', 'Barre de recherche : respecter la casse oui / non', 'Suchleiste: Groß-/Kleinschreibung ein / aus', 'Barra de localizar: diferenciar maiúsculas sim / não', False),
    ('Find bar: close', 'Barra de búsqueda: cerrar', 'Barre de recherche : fermer', 'Suchleiste: schließen', 'Barra de localizar: fechar', False),
    ('Escape too; clears the highlights', 'También Escape; quita los resaltados', 'Échap aussi ; efface les surlignages', 'Auch Escape; entfernt die Markierungen', 'Esc também; limpa os destaques', False),
    ('Move between keys', 'Moverse entre las teclas', 'Se déplacer entre les touches', 'Zwischen Tasten wechseln', 'Mover entre as teclas', False),
    ('The left stick too', 'También el stick izquierdo', 'Le joystick gauche aussi', 'Auch der linke Stick', 'O analógico esquerdo também', False),
    ('Type the key', 'Escribir la tecla', 'Taper la touche', 'Taste eingeben', 'Digitar a tecla', False),
    ('Hold on a letter for accents; D-pad picks, Circle cancels', 'Mantén una letra para los acentos; la cruceta elige, Circle cancela', 'Maintenez une lettre pour les accents ; la croix choisit, Circle annule', 'Buchstaben halten für Akzente; Steuerkreuz wählt, Circle bricht ab', 'Segure uma letra para acentos; o direcional escolhe, Circle cancela', False),
    ('Hold to delete whole words', 'Mantén para borrar palabras enteras', 'Maintenez pour effacer des mots entiers', 'Halten, um ganze Wörter zu löschen', 'Segure para apagar palavras inteiras', False),
    ('Close the keyboard', 'Cerrar el teclado', 'Fermer le clavier', 'Tastatur schließen', 'Fechar o teclado', False),
    ('{Create} too', 'También {Create}', '{Create} aussi', 'Auch {Create}', '{Create} também', False),
    ('Cursor left / right', 'Cursor a la izquierda / derecha', 'Curseur à gauche / droite', 'Cursor links / rechts', 'Cursor para esquerda / direita', False),
    ('Cursor by word', 'Cursor por palabras', 'Curseur mot par mot', 'Cursor wortweise', 'Cursor por palavra', False),
    ('Cursor left / right, scroll up / down', 'Cursor izquierda / derecha, desplazar arriba / abajo', 'Curseur gauche / droite, défiler haut / bas', 'Cursor links / rechts, scrollen auf / ab', 'Cursor esquerda / direita, rolar para cima / baixo', False),
    ('Shift, then Caps lock', 'Mayús, luego Bloq Mayús', 'Maj, puis Verr. Maj', 'Umschalt, dann Feststelltaste', 'Shift, depois Caps Lock', False),
    ('Symbols / letters', 'Símbolos / letras', 'Symboles / lettres', 'Symbole / Buchstaben', 'Símbolos / letras', False),
    ('Numbers in number fields', 'Números en los campos numéricos', 'Chiffres dans les champs numériques', 'Ziffern in Zahlenfeldern', 'Números em campos numéricos', False),
    ('Sites page (address bar)', 'Página de sitios (barra de direcciones)', "Page des sites (barre d'adresse)", 'Website-Seite (Adressleiste)', 'Página de sites (barra de endereço)', True),
    ("In a page's text box: edit tools", 'En un cuadro de texto de la página: herramientas de edición', "Dans un champ de texte de la page : outils d'édition", 'Im Textfeld einer Seite: Bearbeitungswerkzeuge', 'Em uma caixa de texto da página: ferramentas de edição', False),
    ('From the top row; {Cross} uses the word', 'Desde la fila superior; {Cross} usa la palabra', 'Depuis la rangée du haut ; {Cross} utilise le mot', 'Von der obersten Reihe; {Cross} übernimmt das Wort', 'Da fileira de cima; {Cross} usa a palavra', False),
    ('Address suggestions', 'Sugerencias de direcciones', "Suggestions d'adresses", 'Adressvorschläge', 'Sugestões de endereço', False),
    ('Above the words; {Cross} or {Triangle} opens one', 'Encima de las palabras; {Cross} o {Triangle} abre una', 'Au-dessus des mots ; {Cross} ou {Triangle} en ouvre une', 'Über den Wörtern; {Cross} oder {Triangle} öffnet einen', 'Acima das palavras; {Cross} ou {Triangle} abre uma', False),
    ('Sites page: remove a shortcut', 'Página de sitios: quitar un acceso directo', 'Page des sites : retirer un raccourci', 'Website-Seite: Verknüpfung entfernen', 'Página de sites: remover um atalho', False),
    ('Sites page: translate this page', 'Página de sitios: traducir esta página', 'Page des sites : traduire cette page', 'Website-Seite: diese Seite übersetzen', 'Página de sites: traduzir esta página', False),
    ('Sites page: back to the letters', 'Página de sitios: volver a las letras', 'Page des sites : retour aux lettres', 'Website-Seite: zurück zu den Buchstaben', 'Página de sites: voltar às letras', False),
    ('{Triangle} and the touchpad too', 'También {Triangle} y el panel táctil', '{Triangle} et le pavé tactile aussi', 'Auch {Triangle} und das Touchpad', '{Triangle} e o touchpad também', False),
    ('Switch to the tab', 'Ir a la pestaña', "Aller à l'onglet", 'Zum Tab wechseln', 'Ir para a aba', False),
    ('Close the tab', 'Cerrar la pestaña', "Fermer l'onglet", 'Tab schließen', 'Fechar a aba', False),
    ('Mute / unmute the tab', 'Silenciar / activar el sonido de la pestaña', "Couper / rétablir le son de l'onglet", 'Tab stumm / laut schalten', 'Silenciar / ativar o som da aba', False),
    ('Pin / unpin the tab', 'Fijar / soltar la pestaña', "Épingler / détacher l'onglet", 'Tab anheften / lösen', 'Fixar / desafixar a aba', False),
    ('Not for private tabs', 'No en pestañas privadas', 'Pas pour les onglets privés', 'Nicht für private Tabs', 'Não para abas privadas', False),
    ('Choose a tab or a row', 'Elegir una pestaña o una fila', 'Choisir un onglet ou une ligne', 'Tab oder Zeile wählen', 'Escolher uma aba ou uma linha', False),
    ('Page up / down', 'Página arriba / abajo', 'Page précédente / suivante', 'Seite hoch / runter', 'Página acima / abaixo', False),
    ('Save these tabs as a session', 'Guardar estas pestañas como sesión', 'Enregistrer ces onglets comme session', 'Diese Tabs als Sitzung speichern', 'Salvar estas abas como sessão', False),
    ('The row below the tabs', 'La fila debajo de las pestañas', 'La ligne sous les onglets', 'Die Zeile unter den Tabs', 'A linha abaixo das abas', False),
    ('Sessions: open a saved session', 'Sesiones: abrir una sesión guardada', 'Sessions : ouvrir une session enregistrée', 'Sitzungen: gespeicherte Sitzung öffnen', 'Sessões: abrir uma sessão salva', False),
    ('The Sessions row', 'La fila Sesiones', 'La ligne Sessions', 'Die Zeile Sitzungen', 'A linha Sessões', False),
    ('Sessions: rename', 'Sesiones: cambiar nombre', 'Sessions : renommer', 'Sitzungen: umbenennen', 'Sessões: renomear', False),
    ('Sessions: delete', 'Sesiones: eliminar', 'Sessions : supprimer', 'Sitzungen: löschen', 'Sessões: excluir', False),
    ('Press', 'Pulsar', 'Appuyer', 'Drücken', 'Pressionar', False),
    ('Press twice', 'Pulsa dos veces', 'Appuyez deux fois', 'Zweimal drücken', 'Pressione duas vezes', False),
    ('Play / pause', 'Reproducir / pausar', 'Lecture / pause', 'Wiedergabe / Pause', 'Reproduzir / pausar', False),
    ("Full-screen video (YouTube's keys)", 'Vídeo a pantalla completa (teclas de YouTube)', 'Vidéo en plein écran (touches de YouTube)', 'Vollbildvideo (YouTube-Tasten)', 'Vídeo em tela cheia (teclas do YouTube)', False),
    ('Back / forward 10 seconds', 'Atrás / adelante 10 segundos', 'Reculer / avancer de 10 secondes', '10 Sekunden zurück / vor', 'Voltar / avançar 10 segundos', False),
    ('Back / forward 5 seconds', 'Atrás / adelante 5 segundos', 'Reculer / avancer de 5 secondes', '5 Sekunden zurück / vor', 'Voltar / avançar 5 segundos', False),
    ('Full-screen video', 'Vídeo a pantalla completa', 'Vidéo en plein écran', 'Vollbildvideo', 'Vídeo em tela cheia', False),
    ('Volume up / down', 'Subir / bajar el volumen', 'Volume plus / moins', 'Lautstärke hoch / runter', 'Aumentar / diminuir o volume', False),
    ('Captions on / off', 'Subtítulos sí / no', 'Sous-titres oui / non', 'Untertitel ein / aus', 'Legendas sim / não', False),
    ('Mute', 'Silenciar', 'Couper le son', 'Stumm', 'Silenciar', False),
    ('Leave full screen', 'Salir de pantalla completa', 'Quitter le plein écran', 'Vollbild verlassen', 'Sair da tela cheia', False),
    ('{Options} and {Create} too', 'También {Options} y {Create}', '{Options} et {Create} aussi', 'Auch {Options} und {Create}', '{Options} e {Create} também', False),
    ('Options tile while a tab plays: pause, tracks, 10 s, mute', 'Mosaico de Opciones mientras suena una pestaña: pausa, pistas, 10 s, silencio', "Tuile d'Options pendant qu'un onglet joue : pause, pistes, 10 s, muet", 'Kachel in Optionen, während ein Tab spielt: Pause, Titel, 10 s, stumm', 'Bloco em Opções enquanto uma aba toca: pausa, faixas, 10 s, mudo', True),
    ('Options > Now playing > Sleep timer: 15-90 min or end of video', 'Opciones > Reproduciendo > Temporizador de apagado: 15-90 min o fin del vídeo', 'Options > En cours de lecture > Minuterie de veille : 15-90 min ou fin de la vidéo', 'Optionen > Wird abgespielt > Einschlaftimer: 15-90 Min. oder Videoende', 'Opções > Tocando agora > Timer de desligamento: 15-90 min ou fim do vídeo', False),
    ("YouTube TV mode: the remote's arrows", 'Modo TV de YouTube: las flechas del mando a distancia', 'Mode TV de YouTube : les flèches de la télécommande', 'YouTube-TV-Modus: die Pfeiltasten der Fernbedienung', 'Modo TV do YouTube: as setas do controle remoto', False),
    ('{Cross} is Enter, {Circle} is Back', '{Cross} es Intro, {Circle} es Atrás', '{Cross} = Entrée, {Circle} = Retour', '{Cross} ist Enter, {Circle} ist Zurück', '{Cross} é Enter, {Circle} é Voltar', False),
    ('Link or page menu', 'Menú del enlace o de la página', 'Menu du lien ou de la page', 'Link- oder Seitenmenü', 'Menu do link ou da página', False),
    ('Over the page', 'Sobre la página', 'Sur la page', 'Über der Seite', 'Sobre a página', False),
    ('Open the link in a background tab', 'Abrir el enlace en una pestaña en segundo plano', 'Ouvrir le lien dans un onglet en arrière-plan', 'Link in einem Hintergrund-Tab öffnen', 'Abrir o link em uma aba em segundo plano', False),
    ("Then {Cross}: the link menu's first row ({R1} shows it)", 'Luego {Cross}: la primera fila del menú del enlace ({R1} muestra la pestaña)', "Puis {Cross} : la première ligne du menu du lien ({R1} affiche l'onglet)", 'Dann {Cross}: die erste Zeile des Linkmenüs ({R1} zeigt den Tab)', 'Depois {Cross}: a primeira linha do menu do link ({R1} mostra a aba)', False),
    ('Select text', 'Seleccionar texto', 'Sélectionner du texte', 'Text auswählen', 'Selecionar texto', False),
    ('Over text: page menu > Select text', 'Sobre un texto: menú de la página > Seleccionar texto', 'Sur du texte : menu de la page > Sélectionner du texte', 'Über Text: Seitenmenü > Text auswählen', 'Sobre um texto: menu da página > Selecionar texto', False),
    ('Select text: extend by a word', 'Seleccionar texto: ampliar una palabra', "Sélection : étendre d'un mot", 'Textauswahl: um ein Wort erweitern', 'Selecionar texto: estender uma palavra', False),
    ('D-pad up / down: by a line', 'Cruceta arriba / abajo: una línea', "Croix haut / bas : d'une ligne", 'Steuerkreuz auf / ab: um eine Zeile', 'Direcional cima / baixo: uma linha', False),
    ('Select text: Copy, Search, address bar, QR', 'Seleccionar texto: Copiar, Buscar, barra de direcciones, QR', "Sélection : Copier, Rechercher, barre d'adresse, QR", 'Textauswahl: Kopieren, Suchen, Adressleiste, QR', 'Selecionar texto: Copiar, Pesquisar, barra de endereço, QR', False),
    ('Select text: cancel', 'Seleccionar texto: cancelar', 'Sélection : annuler', 'Textauswahl: abbrechen', 'Selecionar texto: cancelar', False),
    ('Screenshot', 'Captura de pantalla', "Capture d'écran", 'Screenshot', 'Captura de tela', False),
    ('Downloads > Saved > Screenshots (not in private tabs)', 'Downloads > Guardado > Capturas (no en pestañas privadas)', "Downloads > Enregistrés > Captures d'écran (pas dans les onglets privés)", 'Downloads > Gespeichert > Screenshots (nicht in privaten Tabs)', 'Downloads > Salvos > Capturas de tela (não em abas privadas)', True),
    ('Copy the text, link or page address', 'Copiar el texto, el enlace o la dirección de la página', "Copier le texte, le lien ou l'adresse de la page", 'Text, Link oder Seitenadresse kopieren', 'Copiar o texto, o link ou o endereço da página', False),
    ('Paste into the text box', 'Pegar en el cuadro de texto', 'Coller dans le champ de texte', 'In das Textfeld einfügen', 'Colar na caixa de texto', False),
    ('Pick the text box with {Cross} first', 'Elige antes el cuadro de texto con {Cross}', "Choisissez d'abord le champ avec {Cross}", 'Zuerst das Textfeld mit {Cross} wählen', 'Escolha antes a caixa de texto com {Cross}', False),
    ('Zoom this site in / out', 'Acercar / alejar este sitio', 'Zoom avant / arrière sur ce site', 'Diese Website vergrößern / verkleinern', 'Aumentar / diminuir o zoom deste site', False),
    ('Remembered for the site', 'Se recuerda para el sitio', 'Mémorisé pour le site', 'Für die Website gemerkt', 'Lembrado para o site', False),
    ('Magnifier: 2x, 3x, off', 'Lupa: 2x, 3x, no', 'Loupe : 2x, 3x, non', 'Lupe: 2x, 3x, aus', 'Lupa: 2x, 3x, desligada', False),
    ('Follows the pointer; {Circle} closes it', 'Sigue al puntero; {Circle} la cierra', 'Suit le pointeur ; {Circle} la ferme', 'Folgt dem Zeiger; {Circle} schließt sie', 'Segue o ponteiro; {Circle} fecha a lupa', False),
    ('Quick tab switcher (most recent first)', 'Cambio rápido de pestaña (las más recientes primero)', "Changement rapide d'onglet (les plus récents d'abord)", 'Schneller Tab-Wechsel (neueste zuerst)', 'Troca rápida de aba (mais recentes primeiro)', False),
    ('Keep {L2} held: {L1} / {R1} or D-pad choose, let go; {Circle} cancels', 'Mantén {L2}: {L1} / {R1} o la cruceta eligen, suelta; {Circle} cancela', 'Gardez {L2} enfoncé : {L1} / {R1} ou la croix choisissent, relâchez ; {Circle} annule', '{L2} gedrückt halten: {L1} / {R1} oder Steuerkreuz wählen, loslassen; {Circle} bricht ab', 'Segure {L2}: {L1} / {R1} ou o direcional escolhem, solte; {Circle} cancela', False),
    ('Save page for later', 'Guardar página para después', 'Enregistrer la page pour plus tard', 'Seite für später speichern', 'Salvar página para depois', False),
    ('Options > Browse, or the page menu (hold {Cross})', 'Opciones > Navegar, o el menú de la página (mantén {Cross})', 'Options > Naviguer, ou le menu de la page (maintenez {Cross})', 'Optionen > Surfen oder das Seitenmenü ({Cross} halten)', 'Opções > Navegar, ou o menu da página (segure {Cross})', False),
    ('Open the saved copy', 'Abrir la copia guardada', 'Ouvrir la copie enregistrée', 'Gespeicherte Kopie öffnen', 'Abrir a cópia salva', False),
    ('Open the live page', 'Abrir la página en línea', 'Ouvrir la page en ligne', 'Live-Seite öffnen', 'Abrir a página on-line', True),
    ('Asks first', 'Pregunta antes', "Demande d'abord", 'Fragt vorher', 'Pergunta antes', False),
    ('Open the file', 'Abrir el archivo', 'Ouvrir le fichier', 'Datei öffnen', 'Abrir o arquivo', False),
    ('Delete a file / cancel a download', 'Eliminar un archivo / cancelar una descarga', 'Supprimer un fichier / annuler un téléchargement', 'Datei löschen / Download abbrechen', 'Excluir um arquivo / cancelar um download', False),
    ('Deleting asks first', 'Antes de eliminar pregunta', 'La suppression demande confirmation', 'Löschen fragt vorher', 'Excluir pede confirmação', False),
    ('Copy to a USB drive', 'Copiar a una unidad USB', 'Copier sur une clé USB', 'Auf ein USB-Laufwerk kopieren', 'Copiar para uma unidade USB', False),
    ('When Omni runs as its own app', 'Cuando Omni funciona como app propia', 'Quand Omni fonctionne comme appli à part', 'Wenn Omni als eigene App läuft', 'Quando o Omni roda como app próprio', False),
    ('Save link target / Save image', 'Guardar destino del enlace / Guardar imagen', "Enregistrer la cible du lien / Enregistrer l'image", 'Linkziel speichern / Bild speichern', 'Salvar destino do link / Salvar imagem', False),
    ('Page menu; to Downloads when Media downloads is on', 'Menú de la página; a Downloads si Media downloads está activado', 'Menu de la page ; vers Downloads si Media downloads est activé', 'Seitenmenü; nach Downloads, wenn Media downloads an ist', 'Menu da página; para Downloads quando o Media downloads está ligado', False),
    ('Saved links', 'Enlaces guardados', 'Liens enregistrés', 'Gespeicherte Links', 'Links salvos', False),
    ('Media downloads on: tap {L2}', 'Con Media downloads activado: toca {L2}', 'Media downloads activé : touchez {L2}', 'Media downloads an: {L2} antippen', 'Media downloads ligado: toque em {L2}', False),
    ('Send this page to Media downloads', 'Enviar esta página a Media downloads', 'Envoyer cette page à Media downloads', 'Diese Seite an Media downloads senden', 'Enviar esta página para o Media downloads', False),
    ('Media downloads on', 'Con Media downloads activado', 'Media downloads activé', 'Media downloads an', 'Media downloads ligado', False),
    ('Open Media downloads', 'Abrir Media downloads', 'Ouvrir Media downloads', 'Media downloads öffnen', 'Abrir o Media downloads', False),
    ('Media downloads on: press both', 'Con Media downloads activado: pulsa ambos', 'Media downloads activé : appuyez sur les deux', 'Media downloads an: beide drücken', 'Media downloads ligado: pressione os dois', False),
    ('Previous / next day', 'Día anterior / siguiente', 'Jour précédent / suivant', 'Vorheriger / nächster Tag', 'Dia anterior / próximo', False),
    ('Delete this visit', 'Eliminar esta visita', 'Supprimer cette visite', 'Diesen Besuch löschen', 'Excluir esta visita', False),
    ('Delete everything from this site', 'Eliminar todo lo de este sitio', 'Supprimer tout ce qui vient de ce site', 'Alles von dieser Website löschen', 'Excluir tudo deste site', False),
    ('Clear the search, then close', 'Borrar la búsqueda y luego cerrar', 'Effacer la recherche, puis fermer', 'Suche leeren, dann schließen', 'Limpar a pesquisa e depois fechar', False),
    # --- Controller shortcuts (OmniButtonMap.h, apply_button_map.py) -------------------------------------------------
    ('Controller shortcuts', 'Atajos del mando', 'Raccourcis de la manette', 'Controller-Kürzel', 'Atalhos do controle', False),
    ('Controller shortcuts...', 'Atajos del mando...', 'Raccourcis de la manette...', 'Controller-Kürzel...', 'Atalhos do controle...', False),
    ('While browsing a page', 'Al navegar por una página', 'En naviguant sur une page', 'Beim Surfen auf einer Seite', 'Ao navegar em uma página', False),
    ('Reset to defaults', 'Restablecer valores predeterminados', 'Rétablir les valeurs par défaut', 'Auf Standard zurücksetzen', 'Restaurar padrões', False),
    ('Controller shortcuts are back to the defaults', 'Los atajos del mando vuelven a los predeterminados', 'Les raccourcis de la manette sont revenus par défaut', 'Controller-Kürzel sind wieder auf Standard', 'Os atalhos do controle voltaram ao padrão', False),
    ('Nothing', 'Nada', 'Rien', 'Nichts', 'Nada', False),
    ('Bookmark this page', 'Añadir esta página a marcadores', 'Ajouter cette page aux favoris', 'Lesezeichen für diese Seite setzen', 'Adicionar esta página aos favoritos', False),
    ('Tab switcher', 'Cambio de pestaña', "Sélecteur d'onglets", 'Tab-Umschalter', 'Alternador de abas', False),
    ('Reader', 'Lectura', 'Lecture', 'Lesen', 'Leitura', False),
    ('Bookmark', 'Marcador', 'Favori', 'Lesezeichen', 'Favorito', False),
    ('QR code', 'Código QR', 'Code QR', 'QR-Code', 'Código QR', False),
    ('Magnifier', 'Lupa', 'Loupe', 'Lupe', 'Lupa', False),
    ('Add shortcut', 'Añadir acceso directo', 'Ajouter un raccourci', 'Verknüpfung hinzufügen', 'Adicionar atalho', False),
    ('Copy', 'Copiar', 'Copier', 'Kopieren', 'Copiar', False),
    ('Paste', 'Pegar', 'Coller', 'Einfügen', 'Colar', False),
    ('Find', 'Buscar', 'Rechercher', 'Suchen', 'Localizar', False),
    ('Default', 'Predeterminado', 'Par défaut', 'Standard', 'Padrão', False),
    ('Also on *', 'También en *', 'Aussi sur *', 'Auch auf *', 'Também em *', False),
    ('Default: *', 'Predeterminado: *', 'Par défaut : *', 'Standard: *', 'Padrão: *', False),
    ('Used by the add-on quick switch (Options > Add-ons)', 'Lo usa el cambio rápido de complementos (Opciones > Complementos)', 'Utilisé par le bouton rapide des modules (Options > Modules complémentaires)', 'Vom Add-on-Schnellschalter belegt (Optionen > Add-ons)', 'Usado pelo atalho rápido de complementos (Opções > Complementos)', True),
    ('No button opens the address bar: point at it and press Cross', 'Ningún botón abre la barra de direcciones: apunta a ella y pulsa Cross', "Aucun bouton n'ouvre la barre d'adresse : pointez-la et appuyez sur Cross", 'Keine Taste öffnet die Adressleiste: darauf zeigen und Cross drücken', 'Nenhum botão abre a barra de endereço: aponte para ela e pressione Cross', False),
    ('No button opens the address bar: point at it and press A', 'Ningún botón abre la barra de direcciones: apunta a ella y pulsa A', "Aucun bouton n'ouvre la barre d'adresse : pointez-la et appuyez sur A", 'Keine Taste öffnet die Adressleiste: darauf zeigen und A drücken', 'Nenhum botão abre a barra de endereço: aponte para ela e pressione A', False),
    ('Tab switcher: Cross switches, Circle cancels', 'Cambio de pestaña: Cross cambia, Circle cancela', "Sélecteur d'onglets : Cross bascule, Circle annule", 'Tab-Umschalter: Cross wechselt, Circle bricht ab', 'Alternador de abas: Cross troca, Circle cancela', False),
    ('Tab switcher: A switches, B cancels', 'Cambio de pestaña: A cambia, B cancela', "Sélecteur d'onglets : A bascule, B annule", 'Tab-Umschalter: A wechselt, B bricht ab', 'Alternador de abas: A troca, B cancela', False),
    ('Your choice (Browser settings > Controller shortcuts)', 'Tu elección (Ajustes del navegador > Atajos del mando)', 'Votre choix (Paramètres du navigateur > Raccourcis de la manette)', 'Deine Wahl (Browser-Einstellungen > Controller-Kürzel)', 'Sua escolha (Configurações do navegador > Atalhos do controle)', False),
    ('Your choice (Browser settings > Controller shortcuts); the add-on quick switch comes first', 'Tu elección (Ajustes del navegador > Atajos del mando); el cambio rápido de complementos va primero', 'Votre choix (Paramètres du navigateur > Raccourcis de la manette) ; le bouton rapide des modules passe avant', 'Deine Wahl (Browser-Einstellungen > Controller-Kürzel); der Add-on-Schnellschalter hat Vorrang', 'Sua escolha (Configurações do navegador > Atalhos do controle); o atalho rápido de complementos vem primeiro', True),
    # --- keyboard hint bar, address bar, sites page ------------------------------------------------------------------
    ('Go', 'Ir', 'Aller', 'Los', 'Ir', False),
    ('Letters', 'Letras', 'Lettres', 'Buchstaben', 'Letras', False),
    ('Insert', 'Insertar', 'Insérer', 'Einfügen', 'Inserir', False),
    ('Choose accent', 'Elegir acento', 'Choisir un accent', 'Akzent wählen', 'Escolher acento', False),
    ('Space', 'Espacio', 'Espace', 'Leerzeichen', 'Espaço', False),
    ('Cursor', 'Cursor', 'Curseur', 'Cursor', 'Cursor', False),
    ('Word', 'Palabra', 'Mot', 'Wort', 'Palavra', False),
    ('Use word', 'Usar palabra', 'Utiliser le mot', 'Wort übernehmen', 'Usar palavra', False),
    ('Type', 'Escribir', 'Saisir', 'Tippen', 'Digitar', False),
    ('Caps off', 'Sin mayúsculas', 'Majuscules désactivées', 'Feststellen aus', 'Maiúsculas desligadas', False),
    ('Caps lock', 'Bloq Mayús', 'Verr. Maj', 'Feststelltaste', 'Caps Lock', False),
    ('Shift', 'Mayús', 'Maj', 'Umschalt', 'Shift', False),
    ('Numbers', 'Números', 'Chiffres', 'Zahlen', 'Números', False),
    ('Symbols', 'Símbolos', 'Symboles', 'Symbole', 'Símbolos', False),
    ('Sites', 'Sitios', 'Sites', 'Websites', 'Sites', False),
    ('Enter', 'Intro', 'Entrée', 'Enter', 'Enter', False),
    ('Send', 'Enviar', 'Envoyer', 'Senden', 'Enviar', False),
    ('Next', 'Siguiente', 'Suivant', 'Weiter', 'Próximo', False),
    ('Search or enter address', 'Busca o escribe una dirección', 'Rechercher ou saisir une adresse', 'Suchen oder Adresse eingeben', 'Pesquise ou digite um endereço', False),
    ('Typing into the webpage field', 'Escribiendo en el campo de la página web', 'Saisie dans le champ de la page web', 'Eingabe in das Feld der Webseite', 'Digitando no campo da página da web', False),
    ('Add this site', 'Añadir este sitio', 'Ajouter ce site', 'Diese Website hinzufügen', 'Adicionar este site', False),
    ('to type', 'para escribir', 'pour saisir', 'zum Tippen', 'para digitar', False),
    ('▲ Up from the top row of keys: suggestions', '▲ Arriba desde la fila superior de teclas: sugerencias', '▲ Haut depuis la rangée supérieure : suggestions', '▲ Von der obersten Tastenreihe nach oben: Vorschläge', '▲ Para cima da fileira de cima: sugestões', False),
    ('▲ Up from the keys to fill', '▲ Arriba desde las teclas para rellenar', '▲ Haut depuis les touches pour remplir', '▲ Von den Tasten nach oben zum Ausfüllen', '▲ Para cima das teclas para preencher', False),
    ('Protection', 'Protección', 'Protection', 'Schutz', 'Proteção', False),
    ('Protected', 'Protegido', 'Protégé', 'Geschützt', 'Protegido', False),
    ('Allowed', 'Permitido', 'Autorisé', 'Erlaubt', 'Permitido', False),
    ('Return to browser', 'Volver al navegador', 'Retour au navigateur', 'Zurück zum Browser', 'Voltar ao navegador', False),
    ('Tab limit reached', 'Límite de pestañas alcanzado', "Limite d'onglets atteinte", 'Tab-Limit erreicht', 'Limite de abas atingido', False),
    ('Private', 'Privada', 'Privé', 'Privat', 'Privada', True),
    ('On (iPhone)', 'Sí (iPhone)', 'Oui (iPhone)', 'Ein (iPhone)', 'Sim (iPhone)', False),
    ('Off (desktop)', 'No (escritorio)', 'Non (ordinateur)', 'Aus (Desktop)', 'Não (computador)', False),
    ('Username', 'Usuario', "Nom d'utilisateur", 'Benutzername', 'Usuário', False),
    ('Password', 'Contraseña', 'Mot de passe', 'Passwort', 'Senha', False),
    ('Password (hidden)', 'Contraseña (oculta)', 'Mot de passe (masqué)', 'Passwort (verborgen)', 'Senha (oculta)', False),
    ('Sign in', 'Iniciar sesión', 'Se connecter', 'Anmelden', 'Entrar', False),
    ('Proxy sign-in', 'Inicio de sesión del proxy', 'Connexion au proxy', 'Proxy-Anmeldung', 'Login do proxy', False),
    ('That username or password was not accepted. Try again.', 'No se aceptó ese usuario o contraseña. Vuelve a intentarlo.', "Ce nom d'utilisateur ou ce mot de passe a été refusé. Réessayez.", 'Benutzername oder Passwort wurde nicht akzeptiert. Versuche es erneut.', 'Esse usuário ou senha não foi aceito. Tente de novo.', False),
    ('This connection is not secure: the password is sent unencrypted.', 'Esta conexión no es segura: la contraseña se envía sin cifrar.', "Cette connexion n'est pas sécurisée : le mot de passe est envoyé en clair.", 'Diese Verbindung ist nicht sicher: Das Passwort wird unverschlüsselt gesendet.', 'Esta conexão não é segura: a senha é enviada sem criptografia.', False),
    ('Text area', 'Área de texto', 'Zone de texte', 'Textbereich', 'Área de texto', False),
    ('Editor', 'Editor', 'Éditeur', 'Editor', 'Editor', False),
    ('Cut', 'Cortar', 'Couper', 'Ausschneiden', 'Recortar', False),
    ('Copied', 'Copiado', 'Copié', 'Kopiert', 'Copiado', False),
    ('Copied *', 'Copiado: *', 'Copié : *', 'Kopiert: *', 'Copiado: *', False),
    ('Desktop site', 'Sitio de escritorio', 'Site pour ordinateur', 'Desktop-Website', 'Site para computador', False),
    ('Mobile site', 'Sitio móvil', 'Site mobile', 'Mobile Website', 'Site para celular', False),
    ('Stay', 'Quedarse', 'Rester', 'Bleiben', 'Ficar', True),
    # --- Display settings (old full-screen settings) ----------------------------------------------------------------
    ('Controller buttons', 'Botones del mando', 'Boutons de la manette', 'Controller-Tasten', 'Botões do controle', False),
    ('Theme', 'Tema', 'Thème', 'Design', 'Tema', False),
    ('Hide bars while reading', 'Ocultar las barras al leer', 'Masquer les barres pendant la lecture', 'Leisten beim Lesen ausblenden', 'Ocultar as barras durante a leitura', False),
    ('Resolution (restart to apply)', 'Resolución (reinicia para aplicar)', 'Résolution (redémarrer pour appliquer)', 'Auflösung (Neustart zum Übernehmen)', 'Resolução (reinicie para aplicar)', False),
    ('Playback stats (this session)', 'Estadísticas de reproducción (esta sesión)', 'Statistiques de lecture (cette session)', 'Wiedergabestatistik (diese Sitzung)', 'Estatísticas de reprodução (esta sessão)', False),
    ('After 3 s without input. Any button brings them back.', 'Tras 3 s sin actividad. Cualquier botón las vuelve a mostrar.', 'Après 3 s sans action. Un bouton les fait revenir.', 'Nach 3 s ohne Eingabe. Jede Taste holt sie zurück.', 'Após 3 s sem uso. Qualquer botão as traz de volta.', False),
    ('(off)', '(desactivado)', '(désactivé)', '(aus)', '(desativado)', False),
    ('Could not save resolution', 'No se pudo guardar la resolución', "Impossible d'enregistrer la résolution", 'Auflösung konnte nicht gespeichert werden', 'Não foi possível salvar a resolução', False),
    ('Resolution saved. Restart Omni to apply.', 'Resolución guardada. Reinicia Omni para aplicarla.', 'Résolution enregistrée. Redémarrez Omni pour l\'appliquer.', 'Auflösung gespeichert. Starte Omni neu, um sie zu übernehmen.', 'Resolução salva. Reinicie o Omni para aplicar.', False),
    ('High contrast on', 'Alto contraste activado', 'Contraste élevé activé', 'Hoher Kontrast an', 'Alto contraste ligado', False),
    ('High contrast off', 'Alto contraste desactivado', 'Contraste élevé désactivé', 'Hoher Kontrast aus', 'Alto contraste desligado', False),
    # --- History -------------------------------------------------------------------------------------------------
    ('Clear history', 'Borrar historial', "Effacer l'historique", 'Verlauf löschen', 'Limpar histórico', False),
    ('Clear history…', 'Borrar historial…', "Effacer l'historique…", 'Verlauf löschen…', 'Limpar histórico…', False),
    ('Removes visits from this console only. Private tabs are never recorded.', 'Solo borra las visitas de esta consola. Las pestañas privadas nunca se registran.', 'Supprime les visites de cette console uniquement. Les onglets privés ne sont jamais enregistrés.', 'Entfernt Besuche nur auf dieser Konsole. Private Tabs werden nie gespeichert.', 'Remove visitas só deste console. Abas privadas nunca são registradas.', False),
    ('Pages you visit appear here (not from private tabs).', 'Aquí aparecen las páginas que visitas (no las de pestañas privadas).', 'Les pages visitées apparaissent ici (pas celles des onglets privés).', 'Besuchte Seiten erscheinen hier (nicht aus privaten Tabs).', 'As páginas que você visita aparecem aqui (exceto as de abas privadas).', False),
    ('Search titles and sites', 'Buscar títulos y sitios', 'Rechercher des titres et des sites', 'Titel und Websites suchen', 'Pesquisar títulos e sites', False),
    ('Type a title or a site', 'Escribe un título o un sitio', 'Saisissez un titre ou un site', 'Titel oder Website eingeben', 'Digite um título ou um site', False),
    ('Last hour', 'Última hora', 'Dernière heure', 'Letzte Stunde', 'Última hora', False),
    ('Today', 'Hoy', "Aujourd'hui", 'Heute', 'Hoje', False),
    ('All time', 'Todo', 'Depuis toujours', 'Gesamter Zeitraum', 'Todo o período', False),
    ('No visits today', 'Hoy no hay visitas', "Aucune visite aujourd'hui", 'Heute keine Besuche', 'Nenhuma visita hoje', False),
    ('Delete site', 'Eliminar sitio', 'Supprimer le site', 'Website löschen', 'Excluir site', False),
    # --- Options menu, page tools, quick menu --------------------------------------------------------------------
    ('This menu', 'Este menú', 'Ce menu', 'Dieses Menü', 'Este menu', False),
    ('Send current link to Downloads', 'Enviar el enlace actual a Downloads', 'Envoyer le lien actuel vers Downloads', 'Aktuellen Link an Downloads senden', 'Enviar o link atual para Downloads', False),
    ('Button labels: Settings > Controller buttons', 'Nombres de botones: Ajustes > Botones del mando', 'Noms des boutons : Paramètres > Boutons de la manette', 'Tastennamen: Einstellungen > Controller-Tasten', 'Nomes dos botões: Configurações > Botões do controle', False),
    ('D-pad: move   Options: close', 'Cruceta: mover   Options: cerrar', 'Croix : déplacer   Options : fermer', 'Steuerkreuz: bewegen   Options: schließen', 'Direcional: mover   Options: fechar', False),
    ('D-pad ◀ ▶ change   zoom: Cross resets', 'Cruceta ◀ ▶ cambiar   zoom: Cross restablece', 'Croix ◀ ▶ modifier   zoom : Cross réinitialise', 'Steuerkreuz ◀ ▶ ändern   Zoom: Cross setzt zurück', 'Direcional ◀ ▶ alterar   zoom: Cross redefine', False),
    ('Zoom (this site)', 'Zoom (este sitio)', 'Zoom (ce site)', 'Zoom (diese Website)', 'Zoom (este site)', False),
    ('Zoom', 'Zoom', 'Zoom', 'Zoom', 'Zoom', False),
    ('Remembered. Cross resets', 'Se recuerda. Cross restablece', 'Mémorisé. Cross réinitialise', 'Gemerkt. Cross setzt zurück', 'Lembrado. Cross redefine', False),
    ('PlayStation buttons', 'Botones de PlayStation', 'Boutons PlayStation', 'PlayStation-Tasten', 'Botões do PlayStation', False),
    ('Xbox buttons', 'Botones de Xbox', 'Boutons Xbox', 'Xbox-Tasten', 'Botões do Xbox', False),
    ('This app', 'Esta app', 'Cette appli', 'Diese App', 'Este app', False),
    ('PS5 app', 'App de PS5', 'Appli PS5', 'PS5-App', 'App do PS5', False),
    ('No apps installed yet', 'Aún no hay apps instaladas', "Aucune appli installée pour l'instant", 'Noch keine Apps installiert', 'Nenhum app instalado ainda', False),
    ('Install Bloom Core with Omnibloom Setup', 'Instala Bloom Core con Omnibloom Setup', 'Installez Bloom Core avec Omnibloom Setup', 'Installiere Bloom Core mit Omnibloom Setup', 'Instale o Bloom Core com o Omnibloom Setup', False),
    ('No earlier page in this tab', 'No hay ninguna página anterior en esta pestaña', 'Aucune page précédente dans cet onglet', 'Keine frühere Seite in diesem Tab', 'Nenhuma página anterior nesta aba', False),
    ('No later page in this tab', 'No hay ninguna página siguiente en esta pestaña', 'Aucune page suivante dans cet onglet', 'Keine spätere Seite in diesem Tab', 'Nenhuma página seguinte nesta aba', False),
    ('Screenshot saved (Downloads > Saved > Screenshots)', 'Captura guardada (Downloads > Guardado > Capturas)', "Capture enregistrée (Downloads > Enregistrés > Captures d'écran)", 'Screenshot gespeichert (Downloads > Gespeichert > Screenshots)', 'Captura salva (Downloads > Salvos > Capturas de tela)', True),
    ('Still saving the last screenshot...', 'Todavía se está guardando la última captura...', "Enregistrement de la dernière capture en cours...", 'Der letzte Screenshot wird noch gespeichert...', 'Ainda salvando a última captura...', False),
    ('Nothing to capture yet', 'Aún no hay nada que capturar', 'Rien à capturer pour le moment', 'Noch nichts zum Aufnehmen', 'Nada para capturar ainda', False),
    ('Not enough memory for a screenshot right now', 'No hay memoria suficiente para una captura ahora mismo', "Pas assez de mémoire pour une capture d'écran pour le moment", 'Gerade nicht genug Speicher für einen Screenshot', 'Sem memória suficiente para uma captura agora', False),
    ("Couldn't save the screenshot (*", 'No se pudo guardar la captura (*', "Impossible d'enregistrer la capture (*", 'Screenshot konnte nicht gespeichert werden (*', 'Não foi possível salvar a captura (*', False),
    ('This page has no source to show', 'Esta página no tiene código fuente que mostrar', "Cette page n'a pas de source à afficher", 'Diese Seite hat keinen Quelltext zum Anzeigen', 'Esta página não tem código-fonte para mostrar', False),
    ('Close a tab first: the source opens in a new tab', 'Cierra antes una pestaña: el código fuente se abre en una pestaña nueva', "Fermez d'abord un onglet : la source s'ouvre dans un nouvel onglet", 'Schließe zuerst einen Tab: Der Quelltext öffnet sich in einem neuen Tab', 'Feche uma aba primeiro: o código-fonte abre em uma nova aba', False),
    ('Getting the page source...', 'Obteniendo el código fuente...', 'Récupération de la source...', 'Quelltext wird geladen...', 'Obtendo o código-fonte...', False),
    ('Page source', 'Código fuente', 'Source de la page', 'Seitenquelltext', 'Código-fonte', False),
    ('View page source', 'Ver código fuente', 'Afficher la source de la page', 'Seitenquelltext anzeigen', 'Ver código-fonte', False),
    ('Dark page', 'Página oscura', 'Page sombre', 'Dunkle Seite', 'Página escura', False),
    ('Dark page on this site', 'Página oscura en este sitio', 'Page sombre sur ce site', 'Dunkle Seite auf dieser Website', 'Página escura neste site', False),
    ('Dark page: turn on', 'Página oscura: activar', 'Page sombre : activer', 'Dunkle Seite: einschalten', 'Página escura: ligar', False),
    ('Dark page: turn off', 'Página oscura: desactivar', 'Page sombre : désactiver', 'Dunkle Seite: ausschalten', 'Página escura: desligar', False),
    ("Pages are blocked from reaching the console's own services", 'Las páginas no pueden acceder a los servicios propios de la consola', 'Les pages ne peuvent pas accéder aux services de la console', 'Seiten können die konsoleneigenen Dienste nicht erreichen', 'As páginas não podem acessar os serviços do próprio console', False),
    ("Warning: pages can now reach the console's own services (loader, FTP, Payload Manager)", 'Atención: ahora las páginas pueden acceder a los servicios de la consola (loader, FTP, Payload Manager)', 'Attention : les pages peuvent maintenant accéder aux services de la console (loader, FTP, Payload Manager)', 'Achtung: Seiten können jetzt die Dienste der Konsole erreichen (Loader, FTP, Payload Manager)', 'Atenção: agora as páginas podem acessar os serviços do console (loader, FTP, Payload Manager)', False),
    ('Older background tabs unload beyond "Tabs kept loaded"', 'Las pestañas en segundo plano más antiguas se descargan más allá de "Pestañas que siguen cargadas"', 'Les onglets en arrière-plan les plus anciens sont déchargés au-delà de « Onglets gardés en mémoire »', 'Ältere Hintergrund-Tabs werden über "Geladen gehaltene Tabs" hinaus entladen', 'Abas antigas em segundo plano são descarregadas além de "Abas mantidas carregadas"', True),
    ('JavaScript JIT on for pages opened from now on (restart Omni to apply everywhere)', 'JIT de JavaScript activado en las páginas que se abran a partir de ahora (reinicia Omni para aplicarlo en todas)', "JIT JavaScript activé pour les pages ouvertes à partir de maintenant (redémarrez Omni pour l'appliquer partout)", 'JavaScript-JIT an für ab jetzt geöffnete Seiten (Omni neu starten, damit es überall gilt)', 'JIT do JavaScript ligado para páginas abertas a partir de agora (reinicie o Omni para aplicar em todas)', False),
    ('JavaScript JIT off for pages opened from now on (restart Omni to apply everywhere)', 'JIT de JavaScript desactivado en las páginas que se abran a partir de ahora (reinicia Omni para aplicarlo en todas)', "JIT JavaScript désactivé pour les pages ouvertes à partir de maintenant (redémarrez Omni pour l'appliquer partout)", 'JavaScript-JIT aus für ab jetzt geöffnete Seiten (Omni neu starten, damit es überall gilt)', 'JIT do JavaScript desligado para páginas abertas a partir de agora (reinicie o Omni para aplicar em todas)', False),
    ('Sites see "Omni" in the user agent from the next page you open', 'Los sitios verán "Omni" en el agente de usuario desde la próxima página que abras', 'Les sites verront « Omni » dans le user agent dès la prochaine page ouverte', 'Websites sehen "Omni" im User-Agent ab der nächsten geöffneten Seite', 'Os sites verão "Omni" no user agent a partir da próxima página aberta', False),
    ('Sites see a plain Safari user agent from the next page you open', 'Los sitios verán un agente de usuario de Safari normal desde la próxima página que abras', 'Les sites verront un user agent Safari standard dès la prochaine page ouverte', 'Websites sehen einen normalen Safari-User-Agent ab der nächsten geöffneten Seite', 'Os sites verão um user agent padrão do Safari a partir da próxima página aberta', False),
    ('YouTube TV mode: YouTube videos and the home page open in the TV app', 'Modo TV de YouTube: los vídeos y la página principal de YouTube se abren en la app de TV', "Mode TV de YouTube : les vidéos et l'accueil de YouTube s'ouvrent dans l'appli TV", 'YouTube-TV-Modus: YouTube-Videos und die Startseite öffnen sich in der TV-App', 'Modo TV do YouTube: os vídeos e a página inicial do YouTube abrem no app de TV', False),
    ('YouTube: the normal website', 'YouTube: el sitio web normal', 'YouTube : le site web normal', 'YouTube: die normale Website', 'YouTube: o site normal', False),
    ('Omni will learn words you type (never passwords, logins or private tabs)', 'Omni aprenderá las palabras que escribas (nunca contraseñas, inicios de sesión ni pestañas privadas)', "Omni apprendra les mots que vous tapez (jamais les mots de passe, identifiants ni onglets privés)", 'Omni lernt Wörter, die du tippst (nie Passwörter, Anmeldungen oder private Tabs)', 'O Omni vai aprender as palavras que você digita (nunca senhas, logins ou abas privadas)', False),
    ('Omni no longer learns words. Clear learned words deletes the saved ones', 'Omni ya no aprende palabras. Borrar palabras aprendidas elimina las guardadas', "Omni n'apprend plus de mots. Effacer les mots appris supprime ceux enregistrés", 'Omni lernt keine Wörter mehr. Gelernte Wörter löschen entfernt die gespeicherten', 'O Omni não aprende mais palavras. Limpar palavras aprendidas apaga as salvas', False),
    ('Ad blocking unavailable: rules could not be loaded.', 'Bloqueo de anuncios no disponible: no se pudieron cargar las reglas.', 'Blocage des publicités indisponible : les règles n\'ont pas pu être chargées.', 'Werbeblocker nicht verfügbar: Regeln konnten nicht geladen werden.', 'Bloqueio de anúncios indisponível: as regras não puderam ser carregadas.', False),
    ("Ad block rules are missing, so most ads aren't blocked. Run Omnibloom Setup > Repair.", 'Faltan las reglas de bloqueo, así que la mayoría de anuncios no se bloquean. Ejecuta Omnibloom Setup > Repair.', "Les règles de blocage manquent : la plupart des publicités ne sont pas bloquées. Lancez Omnibloom Setup > Repair.", 'Werbeblocker-Regeln fehlen, die meisten Anzeigen werden nicht blockiert. Starte Omnibloom Setup > Repair.', 'Faltam as regras de bloqueio, então a maioria dos anúncios não é bloqueada. Execute Omnibloom Setup > Repair.', False),
    ('uBO blocked an ad popup', 'uBO bloqueó una ventana emergente de anuncio', 'uBO a bloqué une pop-up publicitaire', 'uBO hat ein Werbe-Pop-up blockiert', 'O uBO bloqueou um pop-up de anúncio', False),
    ('uBO skipped a redirect / cleaned the link', 'uBO omitió una redirección / limpió el enlace', 'uBO a évité une redirection / nettoyé le lien', 'uBO hat eine Weiterleitung übersprungen / den Link bereinigt', 'O uBO pulou um redirecionamento / limpou o link', False),
    ('Preparing content blocker...', 'Preparando el bloqueador de contenido...', 'Préparation du bloqueur de contenu...', 'Inhaltsblocker wird vorbereitet...', 'Preparando o bloqueador de conteúdo...', False),
    ('Ready', 'Listo', 'Prêt', 'Bereit', 'Pronto', False),
    ('No site to save', 'No hay ningún sitio que guardar', 'Aucun site à enregistrer', 'Keine Website zum Speichern', 'Nenhum site para salvar', False),
    ('Shortcuts are full: remove one first (Square)', 'Los accesos directos están llenos: quita uno primero (Square)', "Les raccourcis sont pleins : retirez-en d'abord un (Square)", 'Verknüpfungen sind voll: zuerst eine entfernen (Square)', 'Os atalhos estão cheios: remova um primeiro (Square)', False),
    ('Shortcuts are full (19): added to bookmarks instead', 'Los accesos directos están llenos (19): se añadió a marcadores', 'Les raccourcis sont pleins (19) : ajouté aux favoris à la place', 'Verknüpfungen sind voll (19): stattdessen als Lesezeichen gespeichert', 'Os atalhos estão cheios (19): adicionado aos favoritos', False),
    ('Only web pages can be shortcuts', 'Solo las páginas web pueden ser accesos directos', 'Seules les pages web peuvent être des raccourcis', 'Nur Webseiten können Verknüpfungen sein', 'Só páginas da web podem ser atalhos', False),
    ('The field is full', 'El campo está lleno', 'Le champ est plein', 'Das Feld ist voll', 'O campo está cheio', False),
    ("Passwords can't be copied", 'Las contraseñas no se pueden copiar', 'Les mots de passe ne peuvent pas être copiés', 'Passwörter können nicht kopiert werden', 'Senhas não podem ser copiadas', False),
    ("This field doesn't support selecting: use Del word or Clear", 'Este campo no permite seleccionar: usa Borrar palabra o Borrar todo', 'Ce champ ne permet pas la sélection : utilisez Suppr. mot ou Effacer', 'Dieses Feld unterstützt keine Auswahl: Wort löschen oder Leeren verwenden', 'Este campo não permite selecionar: use Apagar palavra ou Limpar', True),
    ('Select: move the cursor with L1/R1 (or L2/R2) to select', 'Seleccionar: mueve el cursor con L1/R1 (o L2/R2) para seleccionar', 'Sélection : déplacez le curseur avec L1/R1 (ou L2/R2) pour sélectionner', 'Auswahl: Cursor mit L1/R1 (oder L2/R2) bewegen, um auszuwählen', 'Selecionar: mova o cursor com L1/R1 (ou L2/R2) para selecionar', False),
    ('Switched to the tab that is showing a dialog', 'Se cambió a la pestaña que muestra un cuadro de diálogo', "Passage à l'onglet qui affiche une boîte de dialogue", 'Zum Tab gewechselt, der einen Dialog zeigt', 'Mudou para a aba que mostra uma caixa de diálogo', False),
    ('A background tab is asking you to sign in', 'Una pestaña en segundo plano te pide iniciar sesión', 'Un onglet en arrière-plan vous demande de vous connecter', 'Ein Hintergrund-Tab bittet dich, dich anzumelden', 'Uma aba em segundo plano está pedindo para você entrar', False),
    ('Blocked a dialog from *', 'Cuadro de diálogo bloqueado de *', 'Boîte de dialogue bloquée de *', 'Dialog blockiert von *', 'Caixa de diálogo bloqueada de *', False),
    ('Wait for Media downloads to finish opening', 'Espera a que Media downloads termine de abrirse', "Attendez que Media downloads finisse de s'ouvrir", 'Warte, bis Media downloads fertig geöffnet ist', 'Aguarde o Media downloads terminar de abrir', False),
    ('Opening saved links; the private page was not shared', 'Abriendo enlaces guardados; la página privada no se compartió', "Ouverture des liens enregistrés ; la page privée n'a pas été partagée", 'Gespeicherte Links werden geöffnet; die private Seite wurde nicht geteilt', 'Abrindo links salvos; a página privada não foi compartilhada', False),
    ('Saved links opening cancelled; press L2 to try again', 'Apertura de enlaces guardados cancelada; pulsa L2 para reintentar', 'Ouverture des liens enregistrés annulée ; appuyez sur L2 pour réessayer', 'Öffnen der gespeicherten Links abgebrochen; L2 drücken, um es erneut zu versuchen', 'Abertura dos links salvos cancelada; pressione L2 para tentar de novo', False),
    ('Video found — L2 to review', 'Vídeo encontrado — L2 para revisarlo', 'Vidéo trouvée — L2 pour la voir', 'Video gefunden — L2 zum Ansehen', 'Vídeo encontrado — L2 para revisar', False),
    ('Sleep timer: sound back on', 'Temporizador: sonido reactivado', 'Minuterie : son rétabli', 'Einschlaftimer: Ton wieder an', 'Timer: som de volta', True),
    ('Large pointer is off in test modes', 'El puntero grande está desactivado en los modos de prueba', 'Le grand pointeur est désactivé en mode test', 'Großer Zeiger ist in Testmodi aus', 'O ponteiro grande fica desligado nos modos de teste', False),
    ('Nothing to copy here', 'Aquí no hay nada que copiar', 'Rien à copier ici', 'Hier gibt es nichts zu kopieren', 'Nada para copiar aqui', False),
    ('Nothing copied yet. L2 + Square copies', 'Aún no se ha copiado nada. L2 + Square copia', "Rien n'a encore été copié. L2 + Square copie", 'Noch nichts kopiert. L2 + Square kopiert', 'Nada copiado ainda. L2 + Square copia', False),
    ('Pick a text box first (Cross), then L2 + Triangle pastes', 'Elige antes un cuadro de texto (Cross); luego L2 + Triangle pega', "Choisissez d'abord un champ (Cross), puis L2 + Triangle colle", 'Zuerst ein Textfeld wählen (Cross), dann fügt L2 + Triangle ein', 'Escolha antes uma caixa de texto (Cross); depois L2 + Triangle cola', False),
    ('Opened in a background tab (R1 to view)', 'Abierto en una pestaña en segundo plano (R1 para verla)', 'Ouvert dans un onglet en arrière-plan (R1 pour le voir)', 'In einem Hintergrund-Tab geöffnet (R1 zum Ansehen)', 'Aberto em uma aba em segundo plano (R1 para ver)', False),
    ('No closed tabs to reopen', 'No hay pestañas cerradas que reabrir', 'Aucun onglet fermé à rouvrir', 'Keine geschlossenen Tabs zum Wiederöffnen', 'Nenhuma aba fechada para reabrir', False),
    ('Reopened *', 'Reabierta: *', 'Rouvert : *', 'Wieder geöffnet: *', 'Reaberta: *', False),
    ('That tab was closed', 'Esa pestaña se cerró', 'Cet onglet a été fermé', 'Dieser Tab wurde geschlossen', 'Essa aba foi fechada', False),
    ('Switch to tab', 'Ir a la pestaña', "Aller à l'onglet", 'Zum Tab wechseln', 'Ir para a aba', False),
    ('Switch to private tab', 'Ir a la pestaña privada', "Aller à l'onglet privé", 'Zum privaten Tab wechseln', 'Ir para a aba privada', False),
    ('Current, private', 'Actual, privada', 'Actuel, privé', 'Aktuell, privat', 'Atual, privada', False),
    ('Reloading this tab (it was unloaded to save memory)', 'Recargando esta pestaña (se descargó para ahorrar memoria)', 'Rechargement de cet onglet (déchargé pour économiser la mémoire)', 'Dieser Tab wird neu geladen (er wurde entladen, um Speicher zu sparen)', 'Recarregando esta aba (foi descarregada para economizar memória)', False),
    ('Switch tab', 'Cambiar de pestaña', "Changer d'onglet", 'Tab wechseln', 'Trocar de aba', False),
    ('Release L2 to switch', 'Suelta L2 para cambiar', 'Relâchez L2 pour changer', 'L2 loslassen zum Wechseln', 'Solte L2 para trocar', False),
    ('Release LT to switch', 'Suelta LT para cambiar', 'Relâchez LT pour changer', 'LT loslassen zum Wechseln', 'Solte LT para trocar', False),
    ('This tab', 'Esta pestaña', 'Cet onglet', 'Dieser Tab', 'Esta aba', False),
    ('Pin this tab', 'Fijar esta pestaña', 'Épingler cet onglet', 'Diesen Tab anheften', 'Fixar esta aba', False),
    ('Unpin this tab', 'Soltar esta pestaña', 'Détacher cet onglet', 'Diesen Tab lösen', 'Desafixar esta aba', False),
    ('Pin', 'Fijar', 'Épingler', 'Anheften', 'Fixar', False),
    ('Unpin', 'Soltar', 'Détacher', 'Lösen', 'Desafixar', False),
    ('Mute this tab', 'Silenciar esta pestaña', 'Couper le son de cet onglet', 'Diesen Tab stummschalten', 'Silenciar esta aba', False),
    ('Unmute this tab', 'Activar el sonido de esta pestaña', 'Rétablir le son de cet onglet', 'Ton für diesen Tab an', 'Ativar o som desta aba', False),
    ('Tab muted', 'Pestaña silenciada', 'Onglet muet', 'Tab stummgeschaltet', 'Aba silenciada', False),
    ('Tab sound on', 'Sonido de la pestaña activado', "Son de l'onglet activé", 'Tab-Ton an', 'Som da aba ligado', False),
    ('Playing', 'Reproduciendo', 'Lecture', 'Spielt', 'Tocando', False),
    ('Collapse', 'Contraer', 'Réduire', 'Einklappen', 'Recolher', False),
    ('Expand', 'Expandir', 'Développer', 'Ausklappen', 'Expandir', False),
    ('New group…', 'Nuevo grupo…', 'Nouveau groupe…', 'Neue Gruppe…', 'Novo grupo…', False),
    ('Colour', 'Color', 'Couleur', 'Farbe', 'Cor', False),
    ('Ungroup', 'Desagrupar', 'Dissocier', 'Gruppe auflösen', 'Desagrupar', False),
    ('Hold Cross: group', 'Mantén Cross: agrupar', 'Maintenez Cross : grouper', 'Cross halten: gruppieren', 'Segure Cross: agrupar', False),
    ('Group named "*', 'Grupo llamado "*', 'Groupe nommé « *', 'Gruppe benannt: "*', 'Grupo chamado "*', True),
    ('Add to "*', 'Añadir a "*', 'Ajouter à « *', 'Zu "*', 'Adicionar a "*', True),
    ('Remove from "*', 'Quitar de "*', 'Retirer de « *', 'Entfernen aus "*', 'Remover de "*', True),
    # --- tab memory, sessions ------------------------------------------------------------------------------------------
    ('Memory…', 'Memoria…', 'Mémoire…', 'Speicher…', 'Memória…', False),
    ('Unload all background tabs', 'Descargar todas las pestañas en segundo plano', 'Décharger tous les onglets en arrière-plan', 'Alle Hintergrund-Tabs entladen', 'Descarregar todas as abas em segundo plano', False),
    ('Kept-loaded tabs and tabs playing or loading stay', 'Se mantienen las pestañas fijadas en memoria y las que suenan o cargan', 'Les onglets gardés en mémoire et ceux qui jouent ou chargent restent', 'Geladen gehaltene Tabs und Tabs, die spielen oder laden, bleiben', 'Abas mantidas carregadas e abas tocando ou carregando ficam', True),
    ('Tab unloaded: it reloads when you show it', 'Pestaña descargada: se recarga al mostrarla', "Onglet déchargé : il se recharge quand vous l'affichez", 'Tab entladen: Er lädt neu, wenn du ihn zeigst', 'Aba descarregada: ela recarrega quando você a mostrar', False),
    ("Don't keep loaded", 'No mantener cargada', 'Ne pas garder en mémoire', 'Nicht geladen lassen', 'Não manter carregada', True),
    ('Current', 'Actual', 'Actuel', 'Aktuell', 'Atual', True),
    ('Current, kept loaded', 'Actual, se mantiene cargada', 'Actuel, gardé en mémoire', 'Aktuell, geladen gehalten', 'Atual, mantida carregada', True),
    ('Loaded', 'Cargada', 'Chargé', 'Geladen', 'Carregada', True),
    ('Loaded, pinned', 'Cargada, fijada', 'Chargé, épinglé', 'Geladen, angeheftet', 'Carregada, fixada', True),
    ('Sessions…', 'Sesiones…', 'Sessions…', 'Sitzungen…', 'Sessões…', False),
    ('Save these tabs as a session…', 'Guardar estas pestañas como sesión…', 'Enregistrer ces onglets comme session…', 'Diese Tabs als Sitzung speichern…', 'Salvar estas abas como sessão…', False),
    ('Saved sets of tabs (private tabs are never saved)', 'Conjuntos de pestañas guardados (las pestañas privadas nunca se guardan)', "Ensembles d'onglets enregistrés (les onglets privés ne sont jamais enregistrés)", 'Gespeicherte Tab-Sammlungen (private Tabs werden nie gespeichert)', 'Conjuntos de abas salvos (abas privadas nunca são salvas)', False),
    ('No saved sessions', 'No hay sesiones guardadas', 'Aucune session enregistrée', 'Keine gespeicherten Sitzungen', 'Nenhuma sessão salva', False),
    ('Tabs > Save these tabs as a session', 'Pestañas > Guardar estas pestañas como sesión', 'Onglets > Enregistrer ces onglets comme session', 'Tabs > Diese Tabs als Sitzung speichern', 'Abas > Salvar estas abas como sessão', False),
    ('Open session', 'Abrir sesión', 'Ouvrir la session', 'Sitzung öffnen', 'Abrir sessão', False),
    ('Replace the open tabs', 'Reemplazar las pestañas abiertas', 'Remplacer les onglets ouverts', 'Offene Tabs ersetzen', 'Substituir as abas abertas', False),
    ('Add to the open tabs', 'Añadir a las pestañas abiertas', 'Ajouter aux onglets ouverts', 'Zu den offenen Tabs hinzufügen', 'Adicionar às abas abertas', False),
    ('This session was deleted', 'Esta sesión se eliminó', 'Cette session a été supprimée', 'Diese Sitzung wurde gelöscht', 'Esta sessão foi excluída', False),
    ('All open already', 'Ya están todas abiertas', 'Tous déjà ouverts', 'Alle schon offen', 'Todas já abertas', False),
    ('Open "*', 'Abrir "*', 'Ouvrir « *', 'Öffnen: "*', 'Abrir "*', True),
    ('Renamed to "*', 'Nuevo nombre: "*', 'Renommé en « *', 'Umbenannt in "*', 'Renomeado para "*', False),
    ('Deleted session "*', 'Sesión eliminada: "*', 'Session supprimée : « *', 'Sitzung gelöscht: "*', 'Sessão excluída: "*', False),
    # --- bookmarks, shortcuts, quick access, start page ----------------------------------------------------------------
    ('Showing', 'Mostrando', 'Affichage', 'Anzeige', 'Mostrando', True),
    ('Shortcuts', 'Accesos directos', 'Raccourcis', 'Verknüpfungen', 'Atalhos', False),
    ('Bookmarks and the shortcuts on the new-tab page', 'Marcadores y accesos directos de la página de nueva pestaña', 'Favoris et raccourcis de la page Nouvel onglet', 'Lesezeichen und die Verknüpfungen auf der Neuer-Tab-Seite', 'Favoritos e os atalhos da página de nova aba', False),
    ('L1/R1 move up/down   ▶ new tab / open folder', 'L1/R1 subir/bajar   ▶ pestaña nueva / abrir carpeta', 'L1/R1 monter/descendre   ▶ nouvel onglet / ouvrir le dossier', 'L1/R1 nach oben/unten   ▶ neuer Tab / Ordner öffnen', 'L1/R1 mover para cima/baixo   ▶ nova aba / abrir pasta', False),
    ('No bookmarks: Options → Bookmark page', 'No hay marcadores: Opciones → Añadir a marcadores', 'Aucun favori : Options → Ajouter aux favoris', 'Keine Lesezeichen: Optionen → Lesezeichen setzen', 'Nenhum favorito: Opções → Adicionar aos favoritos', False),
    ('No shortcuts: press L3 on a page to add one', 'No hay accesos directos: pulsa L3 en una página para añadir uno', 'Aucun raccourci : appuyez sur L3 sur une page pour en ajouter un', 'Keine Verknüpfungen: L3 auf einer Seite drücken, um eine hinzuzufügen', 'Nenhum atalho: pressione L3 em uma página para adicionar', False),
    ('Add current page', 'Añadir la página actual', 'Ajouter la page actuelle', 'Aktuelle Seite hinzufügen', 'Adicionar a página atual', False),
    ('No bookmarks: Add current page, or the star in the address bar', 'No hay marcadores: Añadir la página actual, o la estrella de la barra de direcciones', "Aucun favori : Ajouter la page actuelle, ou l'étoile de la barre d'adresse", 'Keine Lesezeichen: Aktuelle Seite hinzufügen oder der Stern in der Adressleiste', 'Nenhum favorito: Adicionar a página atual, ou a estrela na barra de endereço', False),
    ('No bookmark matches "*', 'Ningún marcador coincide con "*', 'Aucun favori ne correspond à « *', 'Kein Lesezeichen passt zu "*', 'Nenhum favorito corresponde a "*', True),
    ('No folder', 'Sin carpeta', 'Aucun dossier', 'Kein Ordner', 'Sem pasta', False),
    ('New folder…', 'Nueva carpeta…', 'Nouveau dossier…', 'Neuer Ordner…', 'Nova pasta…', False),
    ('This bookmark was removed', 'Este marcador se eliminó', 'Ce favori a été supprimé', 'Dieses Lesezeichen wurde entfernt', 'Este favorito foi removido', False),
    ('Name', 'Nombre', 'Nom', 'Name', 'Nome', False),
    ('Folder', 'Carpeta', 'Dossier', 'Ordner', 'Pasta', False),
    ('Move here', 'Mover aquí', 'Déplacer ici', 'Hierher verschieben', 'Mover para cá', False),
    ('Clear the search to reorder', 'Borra la búsqueda para reordenar', 'Effacez la recherche pour réorganiser', 'Suche leeren, um neu zu ordnen', 'Limpe a pesquisa para reordenar', False),
    ('Deleted *', 'Eliminado: *', 'Supprimé : *', 'Gelöscht: *', 'Excluído: *', True),
    ('Quick access', 'Acceso rápido', 'Accès rapide', 'Schnellzugriff', 'Acesso rápido', False),
    ('Back to the default buttons', 'Volver a los botones predeterminados', 'Revenir aux boutons par défaut', 'Zurück zu den Standardtasten', 'Voltar aos botões padrão', False),
    ('Add / remove', 'Añadir / quitar', 'Ajouter / retirer', 'Hinzufügen / entfernen', 'Adicionar / remover', False),
    ('Auto', 'Auto', 'Auto', 'Auto', 'Auto', False),
    ('Background', 'Fondo', 'Arrière-plan', 'Hintergrund', 'Plano de fundo', False),
    ('Clock', 'Reloj', 'Horloge', 'Uhr', 'Relógio', False),
    ('Theme default', 'Predeterminado del tema', 'Par défaut du thème', 'Design-Standard', 'Padrão do tema', False),
    ('Your picture', 'Tu imagen', 'Votre image', 'Dein Bild', 'Sua imagem', False),
    ('Start page background', 'Fondo de la página de inicio', 'Arrière-plan de la page de démarrage', 'Hintergrund des Startbildschirms', 'Plano de fundo da página de início', False),
    ('Use', 'Usar', 'Utiliser', 'Verwenden', 'Usar', False),
    ('Show / hide', 'Mostrar / ocultar', 'Afficher / masquer', 'Ein- / ausblenden', 'Mostrar / ocultar', False),
    ('Background: D-pad ◀ ▶ steps, Cross picks', 'Fondo: la cruceta ◀ ▶ cambia, Cross elige', 'Arrière-plan : croix ◀ ▶ pour parcourir, Cross pour choisir', 'Hintergrund: Steuerkreuz ◀ ▶ blättert, Cross wählt', 'Plano de fundo: direcional ◀ ▶ percorre, Cross escolhe', False),
    ('That saved page is gone', 'Esa página guardada ya no existe', "Cette page enregistrée n'existe plus", 'Diese gespeicherte Seite gibt es nicht mehr', 'Essa página salva não existe mais', False),
    ('Already at the top', 'Ya está arriba del todo', 'Déjà tout en haut', 'Schon ganz oben', 'Já está no topo', False),
    ('Already at the bottom', 'Ya está abajo del todo', 'Déjà tout en bas', 'Schon ganz unten', 'Já está no fim', False),
    ('Clock hidden', 'Reloj oculto', 'Horloge masquée', 'Uhr ausgeblendet', 'Relógio oculto', False),
    ('Clock shown on the start page', 'Reloj visible en la página de inicio', "Horloge affichée sur la page de démarrage", 'Uhr auf dem Startbildschirm eingeblendet', 'Relógio exibido na página de início', False),
    ('Cross: colours and pictures', 'Cross: colores e imágenes', 'Cross : couleurs et images', 'Cross: Farben und Bilder', 'Cross: cores e imagens', False),
    ('Customised', 'Personalizada', 'Personnalisée', 'Angepasst', 'Personalizada', True),
    ('Customised · one column, in your order', 'Personalizada · una columna, en tu orden', 'Personnalisée · une colonne, dans votre ordre', 'Angepasst · eine Spalte, in deiner Reihenfolge', 'Personalizada · uma coluna, na sua ordem', True),
    ('In use', 'En uso', 'Utilisé', 'In Verwendung', 'Em uso', False),
    ('Picture missing: the theme shows', 'Falta la imagen: se muestra el tema', "Image manquante : le thème s'affiche", 'Bild fehlt: Das Design wird angezeigt', 'Imagem ausente: o tema é exibido', False),
    ('Continue watching hidden', 'Seguir viendo oculto', 'Reprendre la lecture masqué', 'Weiterschauen ausgeblendet', 'Continuar assistindo oculto', True),
    ('Continue watching shown on the start page', 'Seguir viendo visible en la página de inicio', 'Reprendre la lecture affiché sur la page de démarrage', 'Weiterschauen auf dem Startbildschirm eingeblendet', 'Continuar assistindo exibido na página de início', True),
    ('Removed from Continue watching', 'Quitado de Seguir viendo', 'Retiré de Reprendre la lecture', 'Aus Weiterschauen entfernt', 'Removido de Continuar assistindo', True),
    # --- reading list, downloads, files, QR, screenshots -------------------------------------------------------------
    ('Save this page', 'Guardar esta página', 'Enregistrer cette page', 'Diese Seite speichern', 'Salvar esta página', False),
    ('Options > Save page for later, or hold Cross on a page', 'Opciones > Guardar página para después, o mantén Cross en una página', 'Options > Enregistrer la page pour plus tard, ou maintenez Cross sur une page', 'Optionen > Seite für später speichern, oder Cross auf einer Seite halten', 'Opções > Salvar página para depois, ou segure Cross em uma página', False),
    ('Open saved copy', 'Abrir copia guardada', 'Ouvrir la copie', 'Kopie öffnen', 'Abrir cópia salva', False),
    ('Open live page', 'Abrir página en línea', 'Ouvrir la page en ligne', 'Live-Seite öffnen', 'Abrir página on-line', True),
    ('Pages in private tabs are never saved', 'Las páginas de pestañas privadas nunca se guardan', 'Les pages des onglets privés ne sont jamais enregistrées', 'Seiten in privaten Tabs werden nie gespeichert', 'Páginas de abas privadas nunca são salvas', False),
    ('Still saving the last page...', 'Todavía se está guardando la última página...', 'Enregistrement de la dernière page en cours...', 'Die letzte Seite wird noch gespeichert...', 'Ainda salvando a última página...', False),
    ('Not enough memory to save this page right now', 'No hay memoria suficiente para guardar esta página ahora mismo', 'Pas assez de mémoire pour enregistrer cette page pour le moment', 'Gerade nicht genug Speicher, um diese Seite zu speichern', 'Sem memória suficiente para salvar esta página agora', False),
    ('Saving page for later...', 'Guardando la página para después...', 'Enregistrement de la page pour plus tard...', 'Seite wird für später gespeichert...', 'Salvando a página para depois...', False),
    ("Couldn't save this page (it didn't answer)", 'No se pudo guardar esta página (no respondió)', "Impossible d'enregistrer cette page (pas de réponse)", 'Diese Seite konnte nicht gespeichert werden (keine Antwort)', 'Não foi possível salvar esta página (sem resposta)', False),
    ('Close a tab first: the saved page opens in a new tab', 'Cierra antes una pestaña: la página guardada se abre en una pestaña nueva', "Fermez d'abord un onglet : la page enregistrée s'ouvre dans un nouvel onglet", 'Schließe zuerst einen Tab: Die gespeicherte Seite öffnet sich in einem neuen Tab', 'Feche uma aba primeiro: a página salva abre em uma nova aba', False),
    ('Still opening a saved page...', 'Todavía se está abriendo una página guardada...', "Ouverture d'une page enregistrée en cours...", 'Eine gespeicherte Seite wird noch geöffnet...', 'Ainda abrindo uma página salva...', False),
    ('Opening saved page...', 'Abriendo la página guardada...', 'Ouverture de la page enregistrée...', 'Gespeicherte Seite wird geöffnet...', 'Abrindo a página salva...', False),
    ('Removed from the reading list', 'Quitada de la lista de lectura', 'Retirée de la liste de lecture', 'Aus der Leseliste entfernt', 'Removida da lista de leitura', False),
    ('This saved page has no live address', 'Esta página guardada no tiene dirección en línea', "Cette page enregistrée n'a pas d'adresse en ligne", 'Diese gespeicherte Seite hat keine Live-Adresse', 'Esta página salva não tem endereço on-line', False),
    ("Couldn't open the saved page: *", 'No se pudo abrir la página guardada: *', "Impossible d'ouvrir la page enregistrée : *", 'Gespeicherte Seite konnte nicht geöffnet werden: *', 'Não foi possível abrir a página salva: *', False),
    ('Saved copy', 'Copia guardada', 'Copie enregistrée', 'Gespeicherte Kopie', 'Cópia salva', False),
    ('Saved text (the page was too large to keep whole)', 'Texto guardado (la página era demasiado grande para guardarla entera)', 'Texte enregistré (la page était trop grande pour être gardée entière)', 'Gespeicherter Text (die Seite war zu groß, um sie ganz zu behalten)', 'Texto salvo (a página era grande demais para guardar inteira)', False),
    ('Loading...', 'Cargando...', 'Chargement...', 'Wird geladen...', 'Carregando...', False),
    ('Nothing saved yet', 'Aún no hay nada guardado', "Rien d'enregistré pour l'instant", 'Noch nichts gespeichert', 'Nada salvo ainda', False),
    ('Downloading', 'Descargando', 'Téléchargement', 'Wird heruntergeladen', 'Baixando', False),
    ('No downloads yet. Files you download are saved in /data/omni/downloads/', 'Aún no hay descargas. Los archivos que descargues se guardan en /data/omni/downloads/', 'Aucun téléchargement. Les fichiers téléchargés sont enregistrés dans /data/omni/downloads/', 'Noch keine Downloads. Heruntergeladene Dateien landen in /data/omni/downloads/', 'Nenhum download ainda. Os arquivos baixados ficam em /data/omni/downloads/', False),
    ('No new tab possible: opening here', 'No se puede abrir otra pestaña: se abre aquí', "Impossible d'ouvrir un nouvel onglet : ouverture ici", 'Kein neuer Tab möglich: wird hier geöffnet', 'Não é possível abrir nova aba: abrindo aqui', False),
    ("Couldn't delete *", 'No se pudo eliminar *', 'Impossible de supprimer *', 'Konnte nicht gelöscht werden: *', 'Não foi possível excluir *', False),
    ('Cancelled *', 'Cancelado: *', 'Annulé : *', 'Abgebrochen: *', 'Cancelado: *', False),
    ('Cancelled', 'Cancelado', 'Annulé', 'Abgebrochen', 'Cancelado', False),
    ('Failed', 'Error', 'Échec', 'Fehlgeschlagen', 'Falhou', False),
    ('Delete / cancel', 'Eliminar / cancelar', 'Supprimer / annuler', 'Löschen / abbrechen', 'Excluir / cancelar', False),
    ('Copy to USB', 'Copiar a USB', 'Copier sur USB', 'Auf USB kopieren', 'Copiar para USB', False),
    ("This file only exists inside the page and can't be saved", 'Este archivo solo existe dentro de la página y no se puede guardar', "Ce fichier n'existe que dans la page et ne peut pas être enregistré", 'Diese Datei existiert nur in der Seite und kann nicht gespeichert werden', 'Este arquivo só existe dentro da página e não pode ser salvo', False),
    ("This link can't be saved", 'Este enlace no se puede guardar', 'Ce lien ne peut pas être enregistré', 'Dieser Link kann nicht gespeichert werden', 'Este link não pode ser salvo', False),
    ('Saving to *', 'Guardando en *', 'Enregistrement dans *', 'Speichern in *', 'Salvando em *', False),
    ('Choose a file to upload', 'Elige un archivo para subir', 'Choisissez un fichier à envoyer', 'Datei zum Hochladen wählen', 'Escolha um arquivo para enviar', False),
    ('Choose files to upload', 'Elige archivos para subir', 'Choisissez des fichiers à envoyer', 'Dateien zum Hochladen wählen', 'Escolha arquivos para enviar', False),
    ('No folders found', 'No se encontraron carpetas', 'Aucun dossier trouvé', 'Keine Ordner gefunden', 'Nenhuma pasta encontrada', False),
    ('Up one folder', 'Subir una carpeta', 'Dossier parent', 'Einen Ordner nach oben', 'Subir uma pasta', False),
    ('Upload this whole folder', 'Subir toda esta carpeta', 'Envoyer tout ce dossier', 'Diesen ganzen Ordner hochladen', 'Enviar esta pasta inteira', False),
    ('Showing every file', 'Se muestran todos los archivos', 'Tous les fichiers sont affichés', 'Alle Dateien werden angezeigt', 'Mostrando todos os arquivos', False),
    ('This folder is empty', 'Esta carpeta está vacía', 'Ce dossier est vide', 'Dieser Ordner ist leer', 'Esta pasta está vazia', False),
    ('Select / open', 'Seleccionar / abrir', 'Sélectionner / ouvrir', 'Auswählen / öffnen', 'Selecionar / abrir', False),
    ('Choose / open', 'Elegir / abrir', 'Choisir / ouvrir', 'Wählen / öffnen', 'Escolher / abrir', False),
    ('All files', 'Todos los archivos', 'Tous les fichiers', 'Alle Dateien', 'Todos os arquivos', False),
    ('D-pad ◀ up a folder', 'Cruceta ◀ subir una carpeta', 'Croix ◀ dossier parent', 'Steuerkreuz ◀ Ordner nach oben', 'Direcional ◀ subir uma pasta', False),
    ('A file picker is already open', 'Ya hay un selector de archivos abierto', 'Un sélecteur de fichiers est déjà ouvert', 'Eine Dateiauswahl ist schon offen', 'Um seletor de arquivos já está aberto', False),
    ('Upload cancelled: the tab changed', 'Subida cancelada: la pestaña cambió', "Envoi annulé : l'onglet a changé", 'Hochladen abgebrochen: Der Tab hat sich geändert', 'Envio cancelado: a aba mudou', False),
    ('A USB copy is already running', 'Ya hay una copia USB en curso', 'Une copie USB est déjà en cours', 'Eine USB-Kopie läuft bereits', 'Uma cópia USB já está em andamento', False),
    ('Copying from the USB drive...', 'Copiando desde la unidad USB...', 'Copie depuis la clé USB...', 'Kopieren vom USB-Laufwerk...', 'Copiando da unidade USB...', False),
    ("Couldn't read *", 'No se pudo leer *', 'Impossible de lire *', 'Konnte nicht gelesen werden: *', 'Não foi possível ler *', False),
    ('Show QR code', 'Mostrar código QR', 'Afficher le code QR', 'QR-Code anzeigen', 'Mostrar código QR', False),
    ('Tracking parameters removed', 'Parámetros de seguimiento quitados', 'Paramètres de suivi retirés', 'Tracking-Parameter entfernt', 'Parâmetros de rastreamento removidos', False),
    ('Only web pages can be shown as a QR code', 'Solo las páginas web se pueden mostrar como código QR', 'Seules les pages web peuvent être affichées en code QR', 'Nur Webseiten können als QR-Code angezeigt werden', 'Só páginas da web podem ser mostradas como código QR', False),
    ('Scan to read this text on your phone', 'Escanéalo para leer este texto en el móvil', 'Scannez pour lire ce texte sur votre téléphone', 'Scannen, um diesen Text auf dem Smartphone zu lesen', 'Escaneie para ler este texto no celular', False),
    ('Selected text', 'Texto seleccionado', 'Texte sélectionné', 'Ausgewählter Text', 'Texto selecionado', False),
    ('No text under the pointer: hold Cross on a word', 'No hay texto bajo el puntero: mantén Cross sobre una palabra', 'Aucun texte sous le pointeur : maintenez Cross sur un mot', 'Kein Text unter dem Zeiger: Cross auf einem Wort halten', 'Nenhum texto sob o ponteiro: segure Cross sobre uma palavra', False),
    ('The selection is gone (the page changed)', 'La selección se perdió (la página cambió)', 'La sélection a disparu (la page a changé)', 'Die Auswahl ist weg (die Seite hat sich geändert)', 'A seleção sumiu (a página mudou)', False),
    ('Nothing to search for', 'No hay nada que buscar', 'Rien à rechercher', 'Nichts zu suchen', 'Nada para pesquisar', False),
    ('Nothing selected: D-pad right selects the next word', 'Nada seleccionado: cruceta derecha selecciona la siguiente palabra', 'Rien de sélectionné : croix droite sélectionne le mot suivant', 'Nichts ausgewählt: Steuerkreuz rechts wählt das nächste Wort', 'Nada selecionado: direcional direita seleciona a próxima palavra', False),
    ('Not enough memory to open this screenshot right now', 'No hay memoria suficiente para abrir esta captura ahora mismo', "Pas assez de mémoire pour ouvrir cette capture d'écran pour le moment", 'Gerade nicht genug Speicher, um diesen Screenshot zu öffnen', 'Sem memória suficiente para abrir esta captura agora', False),
    ("Couldn't delete the screenshot", 'No se pudo eliminar la captura', "Impossible de supprimer la capture d'écran", 'Screenshot konnte nicht gelöscht werden', 'Não foi possível excluir a captura', False),
    ('Screenshot moved to the Downloads trash', 'Captura movida a la papelera de Downloads', "Capture d'écran déplacée dans la corbeille de Downloads", 'Screenshot in den Downloads-Papierkorb verschoben', 'Captura movida para a lixeira do Downloads', False),
    ("Couldn't open this screenshot", 'No se pudo abrir esta captura', "Impossible d'ouvrir cette capture d'écran", 'Dieser Screenshot konnte nicht geöffnet werden', 'Não foi possível abrir esta captura', False),
    ('Opening...', 'Abriendo...', 'Ouverture...', 'Wird geöffnet...', 'Abrindo...', False),
    ("Can't show it", 'No se puede mostrar', "Impossible de l'afficher", 'Nicht anzeigbar', 'Não dá para mostrar', False),
    ('Previous / next', 'Anterior / siguiente', 'Précédent / suivant', 'Zurück / weiter', 'Anterior / próximo', False),
    ('Page', 'Página', 'Page', 'Seite', 'Página', False),
    ('Preview', 'Vista previa', 'Aperçu', 'Vorschau', 'Prévia', False),
    ('Reset to default', 'Restablecer predeterminado', 'Rétablir par défaut', 'Auf Standard zurücksetzen', 'Restaurar padrão', False),
    ('This is how captions will look', 'Así se verán los subtítulos', "Voici l'aspect des sous-titres", 'So sehen die Untertitel aus', 'É assim que as legendas vão ficar', False),
    ('Offline', 'Sin conexión', 'Hors ligne', 'Offline', 'Off-line', False),
    ('Pages that failed offline reload when the connection is back', 'Las páginas que fallaron sin conexión se recargan al volver la conexión', 'Les pages en échec hors ligne se rechargent au retour de la connexion', 'Offline fehlgeschlagene Seiten laden neu, wenn die Verbindung zurück ist', 'Páginas que falharam off-line recarregam quando a conexão volta', False),
    ('Pages that failed offline stay as they are', 'Las páginas que fallaron sin conexión se quedan como están', 'Les pages en échec hors ligne restent telles quelles', 'Offline fehlgeschlagene Seiten bleiben, wie sie sind', 'Páginas que falharam off-line ficam como estão', False),
    ("This page couldn't load", 'Esta página no se pudo cargar', "Cette page n'a pas pu se charger", 'Diese Seite konnte nicht geladen werden', 'Esta página não pôde carregar', False),
    ("You're offline", 'No tienes conexión', 'Vous êtes hors ligne', 'Du bist offline', 'Você está off-line', False),
    ('Retry', 'Reintentar', 'Réessayer', 'Erneut versuchen', 'Tentar de novo', False),
    ('Allow this site', 'Permitir este sitio', 'Autoriser ce site', 'Diese Website erlauben', 'Permitir este site', False),
    ('Blocked', 'Bloqueado', 'Bloqué', 'Blockiert', 'Bloqueado', False),
    ('Connection not private', 'La conexión no es privada', "La connexion n'est pas privée", 'Verbindung nicht privat', 'A conexão não é particular', False),
    ("This site doesn't support a secure connection", 'Este sitio no admite una conexión segura', 'Ce site ne prend pas en charge une connexion sécurisée', 'Diese Website unterstützt keine sichere Verbindung', 'Este site não oferece conexão segura', False),
    ('Go back', 'Volver', 'Revenir en arrière', 'Zurück', 'Voltar', False),
    ('Continue to the http site', 'Continuar al sitio http', 'Continuer vers le site http', 'Weiter zur http-Website', 'Continuar para o site http', False),
    ("Couldn't change uBlock for this site", 'No se pudo cambiar uBlock en este sitio', 'Impossible de modifier uBlock pour ce site', 'uBlock konnte für diese Website nicht geändert werden', 'Não foi possível alterar o uBlock neste site', False),
    # --- site settings, permissions, pop-ups, site list, tweaks ------------------------------------------------------------
    ('Allow', 'Permitir', 'Autoriser', 'Erlauben', 'Permitir', False),
    ('Allow once', 'Permitir una vez', 'Autoriser une fois', 'Einmal erlauben', 'Permitir uma vez', False),
    ('Block', 'Bloquear', 'Bloquer', 'Blockieren', 'Bloquear', False),
    ('Pop-ups and redirects', 'Ventanas emergentes y redirecciones', 'Pop-ups et redirections', 'Pop-ups und Weiterleitungen', 'Pop-ups e redirecionamentos', False),
    ('Open the blocked pop-up', 'Abrir la ventana emergente bloqueada', 'Ouvrir la pop-up bloquée', 'Blockiertes Pop-up öffnen', 'Abrir o pop-up bloqueado', False),
    ('Cookies for *', 'Cookies para *', 'Cookies pour *', 'Cookies für *', 'Cookies para *', False),
    ('Location', 'Ubicación', 'Position', 'Standort', 'Localização', False),
    ('Camera', 'Cámara', 'Caméra', 'Kamera', 'Câmera', False),
    ('Microphone', 'Micrófono', 'Micro', 'Mikrofon', 'Microfone', False),
    ('Notifications', 'Notificaciones', 'Notifications', 'Benachrichtigungen', 'Notificações', False),
    ('Fullscreen', 'Pantalla completa', 'Plein écran', 'Vollbild', 'Tela cheia', False),
    ('Reset permissions for this site', 'Restablecer los permisos de este sitio', 'Réinitialiser les autorisations de ce site', 'Berechtigungen dieser Website zurücksetzen', 'Redefinir as permissões deste site', False),
    ('Pop-ups: Default blocks those a site opens without a press (when uBlock is on)', 'Ventanas emergentes: Predeterminado bloquea las que un sitio abre sin pulsar nada (con uBlock activado)', "Pop-ups : Par défaut bloque celles qu'un site ouvre sans appui (quand uBlock est activé)", 'Pop-ups: Standard blockiert die, die eine Website ohne Tastendruck öffnet (wenn uBlock an ist)', 'Pop-ups: Padrão bloqueia os que um site abre sem um toque (com o uBlock ligado)', True),
    ('No site has saved permissions yet', 'Ningún sitio tiene permisos guardados aún', "Aucun site n'a encore d'autorisations enregistrées", 'Noch keine Website hat gespeicherte Berechtigungen', 'Nenhum site tem permissões salvas ainda', False),
    ('Sites with a saved choice', 'Sitios con una elección guardada', 'Sites avec un choix enregistré', 'Websites mit gespeicherter Auswahl', 'Sites com uma escolha salva', False),
    ('Pop-up blocked. To open it: Options > Site settings > Site permissions', 'Ventana emergente bloqueada. Para abrirla: Opciones > Ajustes del sitio > Permisos de sitios', "Pop-up bloquée. Pour l'ouvrir : Options > Paramètres du site > Autorisations des sites", 'Pop-up blockiert. Zum Öffnen: Optionen > Website-Einstellungen > Website-Berechtigungen', 'Pop-up bloqueado. Para abrir: Opções > Configurações do site > Permissões de sites', False),
    ('No pop-ups blocked in this tab', 'No se bloqueó ninguna ventana emergente en esta pestaña', 'Aucune pop-up bloquée dans cet onglet', 'Keine Pop-ups in diesem Tab blockiert', 'Nenhum pop-up bloqueado nesta aba', False),
    ('Always allow for *', 'Permitir siempre para *', 'Toujours autoriser pour *', 'Immer erlauben für *', 'Sempre permitir para *', False),
    ('Clear this list', 'Borrar esta lista', 'Effacer cette liste', 'Diese Liste leeren', 'Limpar esta lista', False),
    ('The pop-up allow list is full (500 sites)', 'La lista de ventanas emergentes permitidas está llena (500 sitios)', 'La liste des pop-ups autorisées est pleine (500 sites)', 'Die Pop-up-Erlaubnisliste ist voll (500 Websites)', 'A lista de pop-ups permitidos está cheia (500 sites)', False),
    ("uBlock's ad pop-ups can be opened, never always-allowed", 'Las ventanas emergentes de anuncios de uBlock se pueden abrir, nunca permitir siempre', 'Les pop-ups publicitaires de uBlock peuvent être ouvertes, jamais toujours autorisées', 'Werbe-Pop-ups von uBlock lassen sich öffnen, aber nie dauerhaft erlauben', 'Os pop-ups de anúncio do uBlock podem ser abertos, nunca sempre permitidos', False),
    ('Private tab: only for this private session', 'Pestaña privada: solo para esta sesión privada', 'Onglet privé : uniquement pour cette session privée', 'Privater Tab: nur für diese private Sitzung', 'Aba privada: só para esta sessão privada', False),
    ('Saved; pop-ups from this site open without a press', 'Guardado; las ventanas emergentes de este sitio se abren sin pulsar nada', "Enregistré ; les pop-ups de ce site s'ouvrent sans appui", 'Gespeichert; Pop-ups dieser Website öffnen sich ohne Tastendruck', 'Salvo; os pop-ups deste site abrem sem um toque', False),
    ('No press', 'Sin pulsación', 'Sans appui', 'Ohne Tastendruck', 'Sem toque', True),
    ('Open anyway', 'Abrir de todos modos', 'Ouvrir quand même', 'Trotzdem öffnen', 'Abrir mesmo assim', False),
    ('Open it', 'Abrirla', "L'ouvrir", 'Öffnen', 'Abrir', True),
    ('Site: Block', 'Sitio: Bloquear', 'Site : Bloquer', 'Website: Blockieren', 'Site: Bloquear', False),
    ('Clear data for this site', 'Borrar los datos de este sitio', 'Effacer les données de ce site', 'Daten dieser Website löschen', 'Limpar os dados deste site', False),
    ("Couldn't clear site data (no data store)", 'No se pudieron borrar los datos del sitio (no hay almacén de datos)', 'Impossible d\'effacer les données du site (aucun stockage)', 'Websitedaten konnten nicht gelöscht werden (kein Datenspeicher)', 'Não foi possível limpar os dados do site (sem armazenamento)', False),
    ('Search sites…', 'Buscar sitios…', 'Rechercher des sites…', 'Websites durchsuchen…', 'Pesquisar sites…', False),
    ('Square clears', 'Square borra', 'Square efface', 'Square leert', 'Square limpa', False),
    ('Choices made in private tabs are not listed', 'Las elecciones hechas en pestañas privadas no aparecen', 'Les choix faits dans les onglets privés ne sont pas listés', 'Einstellungen aus privaten Tabs werden nicht aufgeführt', 'Escolhas feitas em abas privadas não aparecem', False),
    ('All sites…', 'Todos los sitios…', 'Tous les sites…', 'Alle Websites…', 'Todos os sites…', False),
    ('Every site with settings of its own', 'Cada sitio con ajustes propios', 'Chaque site avec ses propres paramètres', 'Jede Website mit eigenen Einstellungen', 'Cada site com configurações próprias', False),
    ('Nothing is saved for *', 'No hay nada guardado para *', "Rien n'est enregistré pour *", 'Nichts gespeichert für *', 'Nada salvo para *', False),
    ('HTTPS-only', 'Solo HTTPS', 'HTTPS uniquement', 'Nur HTTPS', 'Somente HTTPS', False),
    ('HTTPS-only on this site', 'Solo HTTPS en este sitio', 'HTTPS uniquement sur ce site', 'Nur HTTPS auf dieser Website', 'Somente HTTPS neste site', False),
    ('Always allow pop-ups', 'Permitir siempre ventanas emergentes', 'Toujours autoriser les pop-ups', 'Pop-ups immer erlauben', 'Sempre permitir pop-ups', False),
    ("Couldn't save the uBlock list", 'No se pudo guardar la lista de uBlock', "Impossible d'enregistrer la liste uBlock", 'Die uBlock-Liste konnte nicht gespeichert werden', 'Não foi possível salvar a lista do uBlock', False),
    ('Always dark', 'Siempre oscura', 'Toujours sombre', 'Immer dunkel', 'Sempre escura', True),
    ('Never dark', 'Nunca oscura', 'Jamais sombre', 'Nie dunkel', 'Nunca escura', True),
    ('Autoplay allowed', 'Reproducción automática permitida', 'Lecture automatique autorisée', 'Automatische Wiedergabe erlaubt', 'Reprodução automática permitida', False),
    ('Autoplay without sound', 'Reproducción automática sin sonido', 'Lecture automatique sans son', 'Automatische Wiedergabe ohne Ton', 'Reprodução automática sem som', False),
    ('Autoplay on this site', 'Reproducción automática en este sitio', 'Lecture automatique sur ce site', 'Automatische Wiedergabe auf dieser Website', 'Reprodução automática neste site', False),
    ('Pop-ups allowed', 'Ventanas emergentes permitidas', 'Pop-ups autorisées', 'Pop-ups erlaubt', 'Pop-ups permitidos', False),
    ('Pop-ups blocked', 'Ventanas emergentes bloqueadas', 'Pop-ups bloquées', 'Pop-ups blockiert', 'Pop-ups bloqueados', False),
    ('No site has settings of its own yet', 'Aún no hay sitios con ajustes propios', "Aucun site n'a encore de paramètres propres", 'Noch keine Website hat eigene Einstellungen', 'Nenhum site tem configurações próprias ainda', False),
    ('No sites match', 'Ningún sitio coincide', 'Aucun site ne correspond', 'Keine Website passt', 'Nenhum site corresponde', False),
    ('Cross resets', 'Cross restablece', 'Cross réinitialise', 'Cross setzt zurück', 'Cross redefine', False),
    ('Default (natural)', 'Predeterminado (natural)', 'Par défaut (naturel)', 'Standard (natürlich)', 'Padrão (natural)', True),
    ('Default (off)', 'Predeterminado (no)', 'Par défaut (non)', 'Standard (aus)', 'Padrão (desligado)', False),
    ('On (parent site)', 'Sí (sitio principal)', 'Oui (site parent)', 'Ein (übergeordnete Website)', 'Sim (site principal)', True),
    ('Block all', 'Bloquear todo', 'Tout bloquer', 'Alles blockieren', 'Bloquear tudo', False),
    ('Bigger text', 'Texto más grande', 'Texte plus grand', 'Größerer Text', 'Texto maior', False),
    ('Hide sticky headers/footers', 'Ocultar encabezados/pies fijos', 'Masquer les en-têtes/pieds fixes', 'Fixierte Kopf-/Fußzeilen ausblenden', 'Ocultar cabeçalhos/rodapés fixos', False),
    ('Wider text column', 'Columna de texto más ancha', 'Colonne de texte plus large', 'Breitere Textspalte', 'Coluna de texto mais larga', False),
    ('Larger focus outline', 'Contorno de foco más grande', 'Contour de focus plus grand', 'Größerer Fokusrahmen', 'Contorno de foco maior', False),
    ('Reset tweaks for this site', 'Restablecer los ajustes de página de este sitio', 'Réinitialiser les retouches de ce site', 'Anpassungen dieser Website zurücksetzen', 'Redefinir os ajustes deste site', False),
    ('Cookie banners', 'Avisos de cookies', 'Bannières de cookies', 'Cookie-Banner', 'Avisos de cookies', False),
    ('Upgrade to https', 'Cambiar a https', 'Passer en https', 'Auf https umstellen', 'Mudar para https', False),
    ('Upgrade to https (this session)', 'Cambiar a https (esta sesión)', 'Passer en https (cette session)', 'Auf https umstellen (diese Sitzung)', 'Mudar para https (esta sessão)', False),
    ('Allow http', 'Permitir http', 'Autoriser http', 'http erlauben', 'Permitir http', False),
    ('Allow http (this session)', 'Permitir http (esta sesión)', 'Autoriser http (cette session)', 'http erlauben (diese Sitzung)', 'Permitir http (esta sessão)', False),
    ('Private tab: until Omni closes, private tabs only', 'Pestaña privada: hasta cerrar Omni, solo pestañas privadas', "Onglet privé : jusqu'à la fermeture d'Omni, onglets privés seulement", 'Privater Tab: bis Omni schließt, nur private Tabs', 'Aba privada: até o Omni fechar, só abas privadas', False),
    ('Volume', 'Volumen', 'Volume', 'Lautstärke', 'Volume', False),
    ('Speed', 'Velocidad', 'Vitesse', 'Geschwindigkeit', 'Velocidade', False),
    ('Too many site choices for *', 'Demasiadas elecciones de sitio para *', 'Trop de choix de sites pour *', 'Zu viele Website-Einstellungen für *', 'Escolhas de site demais para *', False),
    # --- add-ons, autofill, passwords --------------------------------------------------------------------------------------
    ('Add-on', 'Complemento', 'Module', 'Add-on', 'Complemento', False),
    ('No add-ons installed', 'No hay complementos instalados', 'Aucun module installé', 'Keine Add-ons installiert', 'Nenhum complemento instalado', False),
    ('Quick switch add-on', 'Complemento de cambio rápido', 'Module du bouton rapide', 'Add-on für den Schnellschalter', 'Complemento do atalho rápido', True),
    ('Quick switch button', 'Botón de cambio rápido', 'Bouton rapide', 'Schnellschalter-Taste', 'Botão de atalho rápido', True),
    ('This add-on is gone', 'Este complemento ya no existe', "Ce module n'existe plus", 'Dieses Add-on gibt es nicht mehr', 'Este complemento não existe mais', False),
    ('Not loaded', 'No cargado', 'Non chargé', 'Nicht geladen', 'Não carregado', False),
    ('On for all sites', 'Activado en todos los sitios', 'Activé sur tous les sites', 'An für alle Websites', 'Ligado em todos os sites', False),
    ('Change it on the add-ons page', 'Cámbialo en la página de complementos', 'Modifiez-le sur la page des modules', 'Auf der Add-on-Seite ändern', 'Altere na página de complementos', False),
    ('Reset settings', 'Restablecer ajustes', 'Réinitialiser les paramètres', 'Einstellungen zurücksetzen', 'Redefinir configurações', False),
    ('Private tabs', 'Pestañas privadas', 'Onglets privés', 'Private Tabs', 'Abas privadas', False),
    ('Source', 'Origen', 'Source', 'Quelle', 'Origem', True),
    ('Never', 'Nunca', 'Jamais', 'Nie', 'Nunca', False),
    ('On here', 'Activado aquí', 'Activé ici', 'Hier an', 'Ligado aqui', False),
    ('Off here', 'Desactivado aquí', 'Désactivé ici', 'Hier aus', 'Desligado aqui', False),
    ('On (not this site)', 'Sí (no en este sitio)', 'Oui (pas sur ce site)', 'Ein (nicht diese Website)', 'Sim (não neste site)', False),
    ('Offer to fill forms', 'Ofrecer rellenar formularios', 'Proposer de remplir les formulaires', 'Ausfüllen von Formularen anbieten', 'Oferecer preenchimento de formulários', False),
    ('Clear the profile', 'Borrar el perfil', 'Effacer le profil', 'Profil löschen', 'Limpar o perfil', False),
    ('One profile, stored in plain text on this console', 'Un perfil, guardado sin cifrar en esta consola', 'Un profil, enregistré en clair sur cette console', 'Ein Profil, unverschlüsselt auf dieser Konsole gespeichert', 'Um perfil, salvo sem criptografia neste console', False),
    ("Fill a form from the page's quick menu or Site settings", 'Rellena un formulario desde el menú rápido de la página o Ajustes del sitio', 'Remplissez un formulaire depuis le menu rapide de la page ou Paramètres du site', 'Formular über das Schnellmenü der Seite oder Website-Einstellungen ausfüllen', 'Preencha um formulário pelo menu rápido da página ou Configurações do site', False),
    ('Fill login', 'Rellenar inicio de sesión', "Remplir l'identifiant", 'Anmeldung ausfüllen', 'Preencher login', False),
    ('Fill form', 'Rellenar formulario', 'Remplir le formulaire', 'Formular ausfüllen', 'Preencher formulário', False),
    ('Fill saved login', 'Rellenar inicio de sesión guardado', "Remplir l'identifiant enregistré", 'Gespeicherte Anmeldung ausfüllen', 'Preencher login salvo', False),
    ('Fill', 'Rellenar', 'Remplir', 'Ausfüllen', 'Preencher', False),
    ('Fill which login?', '¿Qué inicio de sesión rellenar?', 'Quel identifiant remplir ?', 'Welche Anmeldung ausfüllen?', 'Preencher qual login?', False),
    ('Website', 'Sitio web', 'Site web', 'Website', 'Site', False),
    ('Delete this login', 'Eliminar este inicio de sesión', 'Supprimer cet identifiant', 'Diese Anmeldung löschen', 'Excluir este login', False),
    ('Add a login', 'Añadir un inicio de sesión', 'Ajouter un identifiant', 'Anmeldung hinzufügen', 'Adicionar um login', False),
    ('Edit login', 'Editar inicio de sesión', "Modifier l'identifiant", 'Anmeldung bearbeiten', 'Editar login', False),
    ('Save login', 'Guardar inicio de sesión', "Enregistrer l'identifiant", 'Anmeldung speichern', 'Salvar login', False),
    ('Save changes', 'Guardar cambios', 'Enregistrer les modifications', 'Änderungen speichern', 'Salvar alterações', False),
    ('Edit / save', 'Editar / guardar', 'Modifier / enregistrer', 'Bearbeiten / speichern', 'Editar / salvar', False),
    ('Reveal', 'Mostrar', 'Afficher', 'Anzeigen', 'Mostrar', False),
    ('R1 fills the selected login into the current page', 'R1 rellena el inicio de sesión elegido en la página actual', "R1 remplit l'identifiant choisi dans la page actuelle", 'R1 füllt die gewählte Anmeldung in die aktuelle Seite ein', 'R1 preenche o login escolhido na página atual', False),
    ('Typed on this console. Stored encrypted (AES-256-GCM).', 'Escrito en esta consola. Guardado cifrado (AES-256-GCM).', 'Saisi sur cette console. Stocké chiffré (AES-256-GCM).', 'Auf dieser Konsole eingegeben. Verschlüsselt gespeichert (AES-256-GCM).', 'Digitado neste console. Salvo com criptografia (AES-256-GCM).', False),
    ("The password vault can't be opened", 'No se puede abrir el almacén de contraseñas', "Le coffre des mots de passe ne peut pas être ouvert", 'Der Passworttresor kann nicht geöffnet werden', 'O cofre de senhas não pode ser aberto', False),
    ('Unlock with your vault password or PIN', 'Desbloquea con la contraseña del almacén o el PIN', 'Déverrouillez avec le mot de passe du coffre ou le PIN', 'Mit Tresorpasswort oder PIN entsperren', 'Desbloqueie com a senha do cofre ou o PIN', False),
    ("Without one, anyone who can read this console's files can read your passwords", 'Sin él, cualquiera que pueda leer los archivos de esta consola puede leer tus contraseñas', 'Sans lui, quiconque peut lire les fichiers de cette console peut lire vos mots de passe', 'Ohne PIN kann jeder, der die Dateien dieser Konsole lesen kann, deine Passwörter lesen', 'Sem ele, qualquer pessoa que leia os arquivos deste console pode ler suas senhas', False),
    ('Set a PIN (recommended)', 'Establecer un PIN (recomendado)', 'Définir un PIN (recommandé)', 'PIN festlegen (empfohlen)', 'Definir um PIN (recomendado)', False),
    ('Change PIN', 'Cambiar PIN', 'Modifier le PIN', 'PIN ändern', 'Alterar PIN', False),
    ('Remove PIN', 'Quitar PIN', 'Retirer le PIN', 'PIN entfernen', 'Remover PIN', False),
    ('PIN removed', 'PIN quitado', 'PIN retiré', 'PIN entfernt', 'PIN removido', False),
    ('PIN, locked', 'PIN, bloqueado', 'PIN, verrouillé', 'PIN, gesperrt', 'PIN, bloqueado', False),
    ('PIN, unlocked', 'PIN, desbloqueado', 'PIN, déverrouillé', 'PIN, entsperrt', 'PIN, desbloqueado', False),
    ('Lock now', 'Bloquear ahora', 'Verrouiller maintenant', 'Jetzt sperren', 'Bloquear agora', False),
    ('Remove the old unencrypted copy', 'Quitar la copia antigua sin cifrar', "Retirer l'ancienne copie non chiffrée", 'Alte unverschlüsselte Kopie entfernen', 'Remover a cópia antiga sem criptografia', False),
    ('Restored from the backup copy (the vault file was damaged)', 'Restaurado desde la copia de seguridad (el archivo del almacén estaba dañado)', 'Restauré depuis la copie de secours (le fichier du coffre était endommagé)', 'Aus der Sicherungskopie wiederhergestellt (die Tresordatei war beschädigt)', 'Restaurado da cópia de segurança (o arquivo do cofre estava danificado)', False),
    ('No saved logins yet', 'Aún no hay inicios de sesión guardados', "Aucun identifiant enregistré pour l'instant", 'Noch keine gespeicherten Anmeldungen', 'Nenhum login salvo ainda', False),
    ('Passwords locked', 'Contraseñas bloqueadas', 'Mots de passe verrouillés', 'Passwörter gesperrt', 'Senhas bloqueadas', False),
    ('Passwords unlocked', 'Contraseñas desbloqueadas', 'Mots de passe déverrouillés', 'Passwörter entsperrt', 'Senhas desbloqueadas', False),
    ('Passwords are locked: unlock them first', 'Las contraseñas están bloqueadas: desbloquéalas primero', "Les mots de passe sont verrouillés : déverrouillez-les d'abord", 'Passwörter sind gesperrt: zuerst entsperren', 'As senhas estão bloqueadas: desbloqueie primeiro', False),
    ('Passwords are now protected by your PIN', 'Las contraseñas ahora están protegidas por tu PIN', 'Les mots de passe sont maintenant protégés par votre PIN', 'Passwörter sind jetzt durch deine PIN geschützt', 'As senhas agora estão protegidas pelo seu PIN', False),
    ('Use at least 6 characters', 'Usa al menos 6 caracteres', 'Utilisez au moins 6 caractères', 'Mindestens 6 Zeichen verwenden', 'Use pelo menos 6 caracteres', False),
    ("They didn't match: nothing changed", 'No coinciden: no se cambió nada', 'Ils ne correspondent pas : rien n\'a changé', 'Sie stimmen nicht überein: nichts geändert', 'Não coincidem: nada mudou', False),
    ('Protecting the vault...', 'Protegiendo el almacén...', 'Protection du coffre...', 'Tresor wird geschützt...', 'Protegendo o cofre...', False),
    ('That login is for *', 'Ese inicio de sesión es para *', 'Cet identifiant est pour *', 'Diese Anmeldung gilt für *', 'Esse login é para *', False),
    ('The page changed site: nothing was filled', 'La página cambió de sitio: no se rellenó nada', "La page a changé de site : rien n'a été rempli", 'Die Seite hat die Website gewechselt: nichts ausgefüllt', 'A página mudou de site: nada foi preenchido', False),
    ('No sign-in field found on this page', 'No se encontró ningún campo de inicio de sesión en esta página', 'Aucun champ de connexion trouvé sur cette page', 'Kein Anmeldefeld auf dieser Seite gefunden', 'Nenhum campo de login encontrado nesta página', False),
    ('No saved login for this site', 'No hay inicio de sesión guardado para este sitio', "Aucun identifiant enregistré pour ce site", 'Keine gespeicherte Anmeldung für diese Website', 'Nenhum login salvo para este site', False),
    ('A website and a password are needed', 'Se necesitan un sitio web y una contraseña', 'Un site web et un mot de passe sont nécessaires', 'Website und Passwort sind nötig', 'São necessários um site e uma senha', False),
    ("That doesn't look like a website address", 'Eso no parece la dirección de un sitio web', "Cela ne ressemble pas à l'adresse d'un site web", 'Das sieht nicht nach einer Website-Adresse aus', 'Isso não parece um endereço de site', False),
    ("Passwords weren't saved: *", 'No se guardaron las contraseñas: *', "Les mots de passe n'ont pas été enregistrés : *", 'Passwörter wurden nicht gespeichert: *', 'As senhas não foram salvas: *', False),
    ("Login filled: now press Go or the page's sign-in button", 'Inicio de sesión rellenado: ahora pulsa Ir o el botón de inicio de sesión de la página', 'Identifiant rempli : appuyez maintenant sur Aller ou sur le bouton de connexion de la page', 'Anmeldung ausgefüllt: Jetzt Los oder die Anmeldetaste der Seite drücken', 'Login preenchido: agora pressione Ir ou o botão de entrar da página', False),
    ('Username filled (the password goes on the next page)', 'Usuario rellenado (la contraseña va en la página siguiente)', "Nom d'utilisateur rempli (le mot de passe se saisit sur la page suivante)", 'Benutzername ausgefüllt (das Passwort kommt auf der nächsten Seite)', 'Usuário preenchido (a senha vai na próxima página)', False),
    ("The vault can't be opened", 'No se puede abrir el almacén', 'Le coffre ne peut pas être ouvert', 'Der Tresor kann nicht geöffnet werden', 'O cofre não pode ser aberto', False),
    ("The vault key file can't be read", 'No se puede leer el archivo de clave del almacén', 'Le fichier de clé du coffre est illisible', 'Die Schlüsseldatei des Tresors kann nicht gelesen werden', 'O arquivo de chave do cofre não pode ser lido', False),
    ('The vault is locked', 'El almacén está bloqueado', 'Le coffre est verrouillé', 'Der Tresor ist gesperrt', 'O cofre está bloqueado', False),
    ('The vault key file is missing', 'Falta el archivo de clave del almacén', 'Le fichier de clé du coffre est manquant', 'Die Schlüsseldatei des Tresors fehlt', 'O arquivo de chave do cofre está faltando', False),
    # --- apps, media controls, media downloads, send link, misc ------------------------------------------------------------
    ('Add to Apps', 'Añadir a Apps', 'Ajouter aux Applis', 'Zu Apps hinzufügen', 'Adicionar a Apps', False),
    ('Open as app', 'Abrir como app', 'Ouvrir comme appli', 'Als App öffnen', 'Abrir como app', False),
    ('App', 'App', 'Appli', 'App', 'App', False),
    ('No apps yet', 'Aún no hay apps', "Aucune appli pour l'instant", 'Noch keine Apps', 'Nenhum app ainda', False),
    ('On a site: hold Cross, then Add to Apps', 'En un sitio: mantén Cross y luego Añadir a Apps', 'Sur un site : maintenez Cross, puis Ajouter aux Applis', 'Auf einer Website: Cross halten, dann Zu Apps hinzufügen', 'Em um site: segure Cross e depois Adicionar a Apps', False),
    ('Not an app tab any more', 'Ya no es una pestaña de app', "Ce n'est plus un onglet d'appli", 'Kein App-Tab mehr', 'Não é mais uma aba de app', False),
    ('Browser menu', 'Menú del navegador', 'Menu du navigateur', 'Browser-Menü', 'Menu do navegador', False),
    ('Close app', 'Cerrar app', "Fermer l'appli", 'App schließen', 'Fechar app', False),
    ('Leave app mode', 'Salir del modo app', 'Quitter le mode appli', 'App-Modus verlassen', 'Sair do modo app', False),
    ('Left app mode', 'Se salió del modo app', 'Mode appli quitté', 'App-Modus verlassen', 'Saiu do modo app', False),
    ('Already first', 'Ya es la primera', 'Déjà en premier', 'Schon an erster Stelle', 'Já é o primeiro', True),
    ('Full (12)', 'Lleno (12)', 'Plein (12)', 'Voll (12)', 'Cheio (12)', False),
    ("The Downloads tab can't be an app", 'La pestaña Downloads no puede ser una app', "L'onglet Downloads ne peut pas être une appli", 'Der Downloads-Tab kann keine App sein', 'A aba Downloads não pode ser um app', False),
    ('That app was removed', 'Esa app se quitó', 'Cette appli a été retirée', 'Diese App wurde entfernt', 'Esse app foi removido', False),
    ("This page can't be an app", 'Esta página no puede ser una app', 'Cette page ne peut pas être une appli', 'Diese Seite kann keine App sein', 'Esta página não pode ser um app', False),
    ('Still reading this page...', 'Todavía se está leyendo esta página...', 'Lecture de cette page en cours...', 'Diese Seite wird noch gelesen...', 'Ainda lendo esta página...', False),
    ("That app can't be opened", 'Esa app no se puede abrir', 'Cette appli ne peut pas être ouverte', 'Diese App kann nicht geöffnet werden', 'Esse app não pode ser aberto', False),
    ('Bloom Core is not running', 'Bloom Core no se está ejecutando', "Bloom Core n'est pas lancé", 'Bloom Core läuft nicht', 'O Bloom Core não está rodando', False),
    ('Calculator', 'Calculadora', 'Calculatrice', 'Rechner', 'Calculadora', False),
    ('The tab was closed', 'La pestaña se cerró', "L'onglet a été fermé", 'Der Tab wurde geschlossen', 'A aba foi fechada', False),
    ('Back 10 seconds', 'Atrás 10 segundos', 'Reculer de 10 secondes', '10 Sekunden zurück', 'Voltar 10 segundos', False),
    ('Forward 10 seconds', 'Adelante 10 segundos', 'Avancer de 10 secondes', '10 Sekunden vor', 'Avançar 10 segundos', False),
    ('Controls the playing tab, also in the background', 'Controla la pestaña que suena, también en segundo plano', "Contrôle l'onglet en lecture, même en arrière-plan", 'Steuert den spielenden Tab, auch im Hintergrund', 'Controla a aba que está tocando, também em segundo plano', False),
    ('Play', 'Reproducir', 'Lecture', 'Wiedergabe', 'Reproduzir', False),
    ('Pause', 'Pausa', 'Pause', 'Pause', 'Pausar', False),
    ('Next track', 'Pista siguiente', 'Piste suivante', 'Nächster Titel', 'Próxima faixa', False),
    ('Previous track', 'Pista anterior', 'Piste précédente', 'Vorheriger Titel', 'Faixa anterior', False),
    ('Mute tab', 'Silenciar pestaña', "Couper le son de l'onglet", 'Tab stummschalten', 'Silenciar aba', False),
    ('Unmute tab', 'Activar sonido de la pestaña', "Rétablir le son de l'onglet", 'Tab-Ton an', 'Ativar som da aba', False),
    ('Go to tab', 'Ir a la pestaña', "Aller à l'onglet", 'Zum Tab', 'Ir para a aba', False),
    ('Back to the page', 'Volver a la página', 'Retour à la page', 'Zurück zur Seite', 'Voltar à página', False),
    ('Sends the media key; some sites ignore it', 'Envía la tecla multimedia; algunos sitios la ignoran', 'Envoie la touche multimédia ; certains sites l\'ignorent', 'Sendet die Medientaste; manche Websites ignorieren sie', 'Envia a tecla de mídia; alguns sites a ignoram', False),
    ('Restarts the track; at the start sends the media key', 'Reinicia la pista; al principio envía la tecla multimedia', 'Relance la piste ; au début, envoie la touche multimédia', 'Startet den Titel neu; am Anfang sendet es die Medientaste', 'Reinicia a faixa; no início envia a tecla de mídia', False),
    ('The sound fades over 10 seconds, then every tab pauses', 'El sonido se atenúa durante 10 segundos y luego se pausan todas las pestañas', 'Le son baisse pendant 10 secondes, puis tous les onglets se mettent en pause', 'Der Ton wird 10 Sekunden lang leiser, dann pausieren alle Tabs', 'O som diminui por 10 segundos e depois todas as abas pausam', False),
    ('Media downloads is disabled', 'Media downloads está desactivado', 'Media downloads est désactivé', 'Media downloads ist deaktiviert', 'O Media downloads está desativado', False),
    ('Media downloads unavailable; browsing can continue', 'Media downloads no está disponible; puedes seguir navegando', 'Media downloads indisponible ; la navigation peut continuer', 'Media downloads nicht verfügbar; du kannst weitersurfen', 'Media downloads indisponível; a navegação pode continuar', False),
    ('Close a tab to open Media downloads', 'Cierra una pestaña para abrir Media downloads', 'Fermez un onglet pour ouvrir Media downloads', 'Schließe einen Tab, um Media downloads zu öffnen', 'Feche uma aba para abrir o Media downloads', False),
    ('Private links are not shared with Media downloads', 'Los enlaces privados no se comparten con Media downloads', 'Les liens privés ne sont pas partagés avec Media downloads', 'Private Links werden nicht mit Media downloads geteilt', 'Links privados não são compartilhados com o Media downloads', False),
    ('This page cannot be shared as a media link', 'Esta página no se puede compartir como enlace multimedia', 'Cette page ne peut pas être partagée comme lien média', 'Diese Seite kann nicht als Medienlink geteilt werden', 'Esta página não pode ser compartilhada como link de mídia', False),
    ('Media downloads is opening; browsing can continue', 'Media downloads se está abriendo; puedes seguir navegando', "Media downloads s'ouvre ; la navigation peut continuer", 'Media downloads wird geöffnet; du kannst weitersurfen', 'O Media downloads está abrindo; a navegação pode continuar', False),
    ('Media downloads could not start; browsing can continue', 'Media downloads no pudo iniciarse; puedes seguir navegando', "Media downloads n'a pas pu démarrer ; la navigation peut continuer", 'Media downloads konnte nicht starten; du kannst weitersurfen', 'O Media downloads não pôde iniciar; a navegação pode continuar', False),
    ('Media downloads is ready: press L1 + R1 to open it.', 'Media downloads está listo: pulsa L1 + R1 para abrirlo.', "Media downloads est prêt : appuyez sur L1 + R1 pour l'ouvrir.", 'Media downloads ist bereit: L1 + R1 drücken, um es zu öffnen.', 'O Media downloads está pronto: pressione L1 + R1 para abrir.', False),
    ('Opening Media downloads...', 'Abriendo Media downloads...', 'Ouverture de Media downloads...', 'Media downloads wird geöffnet...', 'Abrindo o Media downloads...', False),
    ('Opening saved links...', 'Abriendo enlaces guardados...', 'Ouverture des liens enregistrés...', 'Gespeicherte Links werden geöffnet...', 'Abrindo links salvos...', False),
    ("Couldn't open the link sent from *", 'No se pudo abrir el enlace enviado desde *', "Impossible d'ouvrir le lien envoyé depuis *", 'Link konnte nicht geöffnet werden, gesendet von *', 'Não foi possível abrir o link enviado de *', False),
    ("Couldn't start", 'No se pudo iniciar', 'Impossible de démarrer', 'Konnte nicht starten', 'Não foi possível iniciar', False),
    ('port 8770 is in use', 'el puerto 8770 está en uso', 'le port 8770 est utilisé', 'Port 8770 ist belegt', 'a porta 8770 está em uso', False),
    ('Starting', 'Iniciando', 'Démarrage', 'Wird gestartet', 'Iniciando', False),
    ('Send links from your phone: off', 'Enviar enlaces desde el móvil: no', 'Envoyer des liens depuis votre téléphone : non', 'Links vom Smartphone senden: aus', 'Enviar links do celular: desligado', False),
    ('A picture pointer keeps its own colours', 'Un puntero de imagen mantiene sus propios colores', 'Un pointeur image garde ses propres couleurs', 'Ein Bildzeiger behält seine eigenen Farben', 'Um ponteiro de imagem mantém suas próprias cores', False),
    ('A picture pointer keeps its own outline', 'Un puntero de imagen mantiene su propio contorno', 'Un pointeur image garde son propre contour', 'Ein Bildzeiger behält seinen eigenen Umriss', 'Um ponteiro de imagem mantém seu próprio contorno', False),
    ('Time range', 'Intervalo de tiempo', 'Période', 'Zeitraum', 'Período', False),
    ('Clear data', 'Borrar datos', 'Effacer les données', 'Daten löschen', 'Limpar dados', False),
    ('Clearing...', 'Borrando...', 'Effacement...', 'Wird gelöscht...', 'Limpando...', False),
    ('Last 7 days', 'Últimos 7 días', '7 derniers jours', 'Letzte 7 Tage', 'Últimos 7 dias', False),
    ('Cached files', 'Archivos en caché', 'Fichiers en cache', 'Zwischengespeicherte Dateien', 'Arquivos em cache', False),
    ("Cached files: the whole cache (it can't be cleared by time)", 'Archivos en caché: toda la caché (no se puede borrar por tiempo)', "Fichiers en cache : tout le cache (il ne peut pas être effacé par période)", 'Zwischengespeicherte Dateien: der ganze Cache (lässt sich nicht nach Zeit löschen)', 'Arquivos em cache: o cache inteiro (não dá para limpar por período)', False),
    ('Nothing to clear.', 'No hay nada que borrar.', 'Rien à effacer.', 'Nichts zu löschen.', 'Nada para limpar.', False),
    ('Match case: on', 'Distinguir mayúsculas: sí', 'Respecter la casse : oui', 'Groß-/Kleinschreibung: ein', 'Diferenciar maiúsculas: sim', False),
    ('Match case: off', 'Distinguir mayúsculas: no', 'Respecter la casse : non', 'Groß-/Kleinschreibung: aus', 'Diferenciar maiúsculas: não', False),
    ('Reached the top of the page — back to the last match', 'Se llegó al principio de la página — vuelta a la última coincidencia', 'Haut de la page atteint — retour au dernier résultat', 'Seitenanfang erreicht — zurück zum letzten Treffer', 'Chegou ao topo da página — voltando ao último resultado', False),
    ('Controller light & rumble on', 'Luz y vibración del mando activadas', 'Lumière et vibrations de la manette activées', 'Controller-Licht & Vibration an', 'Luz e vibração do controle ligadas', False),
    ('Controller light & rumble off', 'Luz y vibración del mando desactivadas', 'Lumière et vibrations de la manette désactivées', 'Controller-Licht & Vibration aus', 'Luz e vibração do controle desligadas', False),
    ('Scheduled', 'Programada', 'Programmé', 'Zeitplan', 'Programada', True),
    ('Scheduled (on now)', 'Programada (activada ahora)', 'Programmé (activé maintenant)', 'Zeitplan (jetzt an)', 'Programada (ligada agora)', True),
    ('Scheduled (off now)', 'Programada (desactivada ahora)', 'Programmé (désactivé maintenant)', 'Zeitplan (jetzt aus)', 'Programada (desligada agora)', True),
    ('Default (schedule, dark now)', 'Predeterminado (programado, oscuro ahora)', 'Par défaut (programmé, sombre maintenant)', 'Standard (Zeitplan, jetzt dunkel)', 'Padrão (programado, escuro agora)', True),
    ('Default (schedule, light now)', 'Predeterminado (programado, claro ahora)', 'Par défaut (programmé, clair maintenant)', 'Standard (Zeitplan, jetzt hell)', 'Padrão (programado, claro agora)', True),
    ('Too many wrong tries: wait *', 'Demasiados intentos fallidos: espera *', 'Trop d\'essais incorrects : patientez *', 'Zu viele Fehlversuche: warte *', 'Tentativas erradas demais: aguarde *', False),
    # --- settings search ------------------------------------------------------------------------------------------------
    ('Type a few letters', 'Escribe unas letras', 'Tapez quelques lettres', 'Ein paar Buchstaben eingeben', 'Digite algumas letras', False),
    ('No settings match', 'Ningún ajuste coincide', 'Aucun paramètre ne correspond', 'Keine Einstellung passt', 'Nenhuma configuração corresponde', False),
    ('Try another word, or Square to show all', 'Prueba otra palabra, o Square para mostrar todo', 'Essayez un autre mot, ou Square pour tout afficher', 'Anderes Wort versuchen oder Square für alle', 'Tente outra palavra, ou Square para mostrar tudo', False),
    ('Clear search', 'Borrar búsqueda', 'Effacer la recherche', 'Suche leeren', 'Limpar pesquisa', False),
    ('Search settings', 'Buscar ajustes', 'Rechercher un paramètre', 'Einstellungen durchsuchen', 'Pesquisar configurações', False),
    ('No settings match "*', 'Ningún ajuste coincide con "*', 'Aucun paramètre ne correspond à « *', 'Keine Einstellung passt zu "*', 'Nenhuma configuração corresponde a "*', True),
]


def c_lit(s):
    """A C++ string literal of s's UTF-8 bytes (ASCII source; a hex escape followed by a hex digit splits the literal)."""
    out, prev_hex = ['"'], False
    for b in s.encode('utf-8'):
        ch = chr(b)
        if b >= 0x80:
            out.append('\\x%02x' % b); prev_hex = True; continue
        if prev_hex and ch in '0123456789abcdefABCDEF':
            out.append('" "')
        prev_hex = False
        if ch in '"\\':
            out.append('\\' + ch)
        elif b < 0x20:
            out.append('\\x%02x' % b); prev_hex = True
        else:
            out.append(ch)
    out.append('"')
    return ''.join(out)


TABLE = T + T2


def fmt_specs(s):
    """The printf conversions of s in order (the C++ OL10::formatSpecs, same rules); '!' for a bad one."""
    out, i = [], 0
    while i < len(s):
        if s[i] != '%':
            i += 1
            continue
        if s[i + 1:i + 2] == '%':
            i += 2
            continue
        j = i + 1
        while j < len(s) and s[j] in '-+ #0':
            j += 1
        while j < len(s) and s[j].isdigit():
            j += 1
        if j < len(s) and s[j] == '.':
            j += 1
            while j < len(s) and s[j].isdigit():
                j += 1
        ln = ''
        while j < len(s) and s[j] in 'hlLzjt':
            ln += s[j]
            j += 1
        if j >= len(s) or s[j] not in 'diouxXeEfgGcsp':
            return '!'
        out.append(ln + s[j])
        i = j + 1
    return ''.join(out)


def brace_tokens(s):
    import re
    return sorted(re.findall(r'\{[A-Za-z0-9]+\}', s))


def table_cpp():
    seen = set()
    lines = []
    for row in TABLE:
        en, es, fr, de, pt, unsure = row
        if en in seen:
            sys.exit('table: duplicate key %r' % en)
        seen.add(en)
        tr = (es, fr, de, pt)
        if all(t is None for t in tr):   # English-only (a name)
            lines.append('        { %s, nullptr, nullptr, nullptr, nullptr, false },' % c_lit(en))
            continue
        for t in tr:
            if (t is None or en.endswith('*') != t.endswith('*') or '\t' in t or '\n' in t or not t
                    or fmt_specs(en) != fmt_specs(t) or brace_tokens(en) != brace_tokens(t)):
                sys.exit('table: bad translation for %r: %r' % (en, t))
        lines.append('        { %s, %s, %s, %s, %s, %s },' % (c_lit(en), c_lit(es), c_lit(fr), c_lit(de), c_lit(pt),
                                                             'true' if unsure else 'false'))
    return '\n'.join(lines)


PURE = r'''// OMNI_UI_LANG_V1: the pure part of Omni's own UI in other languages (no SDL, no WebKit, no file I/O).
// Written by tools/apply_ui_lang.py (the table is generated there, from readable UTF-8); the shell side is
// OmniUiLangShell.h. Tested on the host with g++ (tools/test_ui_lang.cpp).
// English is the key: a drawn text is looked up and replaced by its translation, or stays English. Keys ending in '*'
// are prefixes ("Sent to Downloads: *" also covers "Sent to Downloads: clip.mp4"). Only drawing translates: the code
// keeps comparing the English labels, titles and statuses.
// OMNI_UI_LANG_V1_R2: stage 2 - English-only rows (nullptr translations, never loaded), printf / {Token} checks on
// every entry (a translation whose conversions or tokens differ from its key is refused: format keys are safe to
// snprintf), accent / case folding for settings search, the two-language settings search order, the hint bar's
// width cap.
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstring>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace OmniUiLang {

constexpr size_t kFileMax = 256 * 1024;  // /data/omni/lang/<code>.txt is read up to this many bytes
constexpr size_t kEntryMax = 4000;       // entries taken from one file
constexpr size_t kTextMax = 600;         // longest key or translation taken from a file
constexpr int kParamLang = 1;            // SCE_SYSTEM_SERVICE_PARAM_ID_LANG

struct Row { const char* en; const char* es; const char* fr; const char* de; const char* pt; bool unsure; };
inline constexpr const char* kBuiltin[] = { "es", "fr", "de", "pt" };   // Row columns 1..4

inline const Row* rows(size_t& count)
{
    static const Row table[] = {
@TABLE@
    };
    count = sizeof(table) / sizeof(table[0]);
    return table;
}

// "pt_BR" -> "pt", "ES" -> "es", "auto" -> "auto"; anything that is not 2-3 letters (+ region) -> "".
inline std::string normCode(const std::string& in)
{
    std::string c;
    for (char ch : in) {
        if (ch == '-' || ch == '_') break;
        if (ch >= 'A' && ch <= 'Z') ch = char(ch - 'A' + 'a');
        if (ch < 'a' || ch > 'z') return std::string();
        c += ch;
    }
    if (c == "auto") return c;
    return c.size() == 2 || c.size() == 3 ? c : std::string();
}
// The PS5 system language (SCE_SYSTEM_PARAM_LANG_* value) as a language code; unknown / failed (< 0) -> "en".
inline std::string fromSystem(int v)
{
    static const char* const codes[] = { "ja", "en", "fr", "es", "de", "it", "nl", "pt", "ru", "ko", "zh", "zh", "fi", "sv",
        "da", "no", "pl", "pt", "en", "tr", "es", "ar", "fr", "cs", "hu", "el", "ro", "th", "vi", "id", "uk" };
    return v >= 0 && v < int(sizeof(codes) / sizeof(codes[0])) ? codes[v] : "en";
}
inline int column(const std::string& code)
{
    for (int i = 0; i < 4; ++i) if (code == kBuiltin[i]) return i;
    return -1;
}
inline const char* nativeName(const std::string& code)
{
    if (code == "en") return "English";
    if (code == "es") return "Espa\xc3\xb1ol";
    if (code == "fr") return "Fran\xc3\xa7" "ais";
    if (code == "de") return "Deutsch";
    if (code == "pt") return "Portugu\xc3\xaas";
    return nullptr;
}
// The saved choice (/data/omni/ui-lang.txt): the first word of the first line that is not empty or a comment;
// missing or not a language code -> "auto".
inline std::string parseChoice(const std::string& text)
{
    size_t i = 0;
    while (i < text.size()) {
        size_t e = text.find('\n', i);
        if (e == std::string::npos) e = text.size();
        const std::string line = text.substr(i, e - i);
        i = e + 1;
        const size_t a = line.find_first_not_of(" \t\r");
        if (a == std::string::npos || line[a] == '#') continue;
        const size_t b = line.find_first_of(" \t\r#", a);
        const std::string c = normCode(line.substr(a, b == std::string::npos ? std::string::npos : b - a));
        return c.empty() ? std::string("auto") : c;
    }
    return "auto";
}
// The Language row cycles: auto, en, the built-in ones; a code set by hand in the file (e.g. "it") stays in the cycle.
inline std::vector<std::string> choices(const std::string& current)
{
    std::vector<std::string> v = { "auto", "en", "es", "fr", "de", "pt" };
    if (!current.empty() && std::find(v.begin(), v.end(), current) == v.end()) v.push_back(current);
    return v;
}
inline std::string step(const std::string& current, int dir)
{
    const std::vector<std::string> v = choices(current);
    const size_t n = v.size();
    size_t i = size_t(std::find(v.begin(), v.end(), current) - v.begin());
    if (i >= n) i = 0;
    return v[(i + (dir < 0 ? n - 1 : 1)) % n];
}

inline bool oneOf(char c, const char* set) { return c && std::strchr(set, c); }
// The printf conversions of s in order ("dd" for "Page %d of %d"; length modifiers kept: "ld"); "%%" is none; a '%'
// that starts no valid conversion makes the whole result "!".
inline std::string formatSpecs(const std::string& s)
{
    std::string out;
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] != '%') continue;
        if (i + 1 < s.size() && s[i + 1] == '%') { ++i; continue; }
        size_t j = i + 1;
        while (j < s.size() && oneOf(s[j], "-+ #0")) ++j;
        while (j < s.size() && s[j] >= '0' && s[j] <= '9') ++j;
        if (j < s.size() && s[j] == '.') { ++j; while (j < s.size() && s[j] >= '0' && s[j] <= '9') ++j; }
        while (j < s.size() && oneOf(s[j], "hlLzjt")) out += s[j++];
        if (j >= s.size() || !oneOf(s[j], "diouxXeEfgGcsp")) return "!";
        out += s[j];
        i = j;
    }
    return out;
}
// The {Token}s of s (the Controls guide's {Cross}, {Options} ...), sorted.
inline std::vector<std::string> braceTokens(const std::string& s)
{
    std::vector<std::string> v;
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] != '{') continue;
        size_t j = i + 1;
        while (j < s.size() && ((s[j] >= 'A' && s[j] <= 'Z') || (s[j] >= 'a' && s[j] <= 'z') || (s[j] >= '0' && s[j] <= '9'))) ++j;
        if (j > i + 1 && j < s.size() && s[j] == '}') { v.push_back(s.substr(i, j - i + 1)); i = j; }
    }
    std::sort(v.begin(), v.end());
    return v;
}
// A translation may stand for its key: same printf conversions, same {Token}s, both or neither a prefix ('*').
inline bool compatible(const std::string& en, const std::string& tr)
{
    if (en.empty() || tr.empty() || (en.back() == '*') != (tr.back() == '*')) return false;
    return formatSpecs(en) == formatSpecs(tr) && formatSpecs(tr) != "!" && braceTokens(en) == braceTokens(tr);
}
// For matching only: ASCII and Latin-1 letters lower-cased, accents dropped ("Configuración" -> "configuracion",
// "Über" -> "uber", "ß" -> "ss", "Ç" -> "c"). Other bytes are kept as they are.
inline std::string fold(const std::string& s)
{
    // U+00C0 .. U+00FF, index c - 0xC0: the base letter, 0 = keep the two bytes
    static const char* const base =
        "aaaaaaaceeeeiiii" "dnooooo\0ouuuuy\0s"   // C0..DF (D7 x, DE thorn kept; DF sharp s -> "ss" below)
        "aaaaaaaceeeeiiii" "dnooooo\0ouuuuy\0y";  // E0..FF (F7 division, FE thorn kept)
    std::string o;
    o.reserve(s.size());
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        if (c >= 'A' && c <= 'Z') { o += char(c - 'A' + 'a'); continue; }
        if (c == 0xC3 && i + 1 < s.size()) {
            const unsigned char d = static_cast<unsigned char>(s[i + 1]);
            if (d >= 0x80 && d <= 0xBF) {
                const unsigned k = d + 0x40 - 0xC0;   // the code point - 0xC0
                if (d == 0x9F) { o += "ss"; ++i; continue; }
                if (base[k]) { o += base[k]; ++i; continue; }
            }
        }
        if (c == 0xC5 && i + 1 < s.size() && (static_cast<unsigned char>(s[i + 1]) == 0x92 || static_cast<unsigned char>(s[i + 1]) == 0x93)) { o += "oe"; ++i; continue; }
        o += char(c);
    }
    return o;
}
// The hint bar: label widths (layout px) and the room they share. 0 = they fit; else the one cap every label is cut
// to (the narrow ones keep their width, the wide ones share what is left equally), at least minCap.
inline int fitCap(const std::vector<int>& widths, int room, int minCap = 24)
{
    long total = 0;
    for (int w : widths) total += w;
    if (total <= room) return 0;
    std::vector<int> v = widths;
    std::sort(v.begin(), v.end());
    long used = 0;
    for (size_t i = 0; i < v.size(); ++i) {
        const long cap = (long(room) - used) / long(v.size() - i);
        if (cap < v[i]) return int(std::max<long>(minCap, cap));
        used += v[i];
    }
    return minCap;
}
// Settings search in two languages: a: each entry's tier matched in English, b: in the shown language; none: the
// no-match tier. The entries that match either way, best tier first, the list order within a tier.
inline std::vector<size_t> bestOf(const std::vector<int>& a, const std::vector<int>& b, int none)
{
    std::vector<std::pair<int, size_t>> hits;
    for (size_t i = 0; i < a.size() && i < b.size(); ++i) {
        const int t = std::min(a[i], b[i]);
        if (t != none) hits.push_back({ t, i });
    }
    std::stable_sort(hits.begin(), hits.end(), [](const auto& x, const auto& y) { return x.first < y.first; });
    std::vector<size_t> out;
    for (const auto& h : hits) out.push_back(h.second);
    return out;
}
// OmniSettingsSearch::view's steadiness rule on a ready order: ids shown so far first (in that order, still present),
// then the newly matching ones, remembered in `shown`.
inline std::vector<size_t> keepShown(const std::vector<size_t>& fresh, const std::vector<int>& ids, std::vector<int>& shown)
{
    std::vector<size_t> out;
    std::vector<bool> used(ids.size(), false);
    for (int id : shown)
        for (size_t i = 0; i < ids.size(); ++i)
            if (!used[i] && ids[i] == id) { used[i] = true; out.push_back(i); break; }
    for (size_t i : fresh)
        if (i < ids.size() && !used[i]) { used[i] = true; out.push_back(i); shown.push_back(ids[i]); }
    return out;
}

class Table {
public:
    void clear() { exact_.clear(); prefixes_.clear(); }
    bool empty() const { return exact_.empty() && prefixes_.empty(); }
    size_t size() const { return exact_.size() + prefixes_.size(); }
    // "Key*" with "Translation*" is a prefix entry (both or neither end in '*'). A later entry replaces an earlier one.
    // OMNI_UI_LANG_V1_R2: refused unless compatible() (same printf conversions and {Token}s as the key).
    bool add(const std::string& en, const std::string& tr)
    {
        if (en.empty() || tr.empty()) return false;
        const bool pk = en.back() == '*', pv = tr.back() == '*';
        if (pk != pv || !compatible(en, tr)) return false;
        if (!pk) { exact_[en] = tr; return true; }
        const std::string k = en.substr(0, en.size() - 1), t = tr.substr(0, tr.size() - 1);
        if (k.empty()) return false;
        for (auto& p : prefixes_) if (p.first == k) { p.second = t; return true; }
        prefixes_.emplace_back(k, t);
        std::stable_sort(prefixes_.begin(), prefixes_.end(), [](const auto& a, const auto& b) { return a.first.size() > b.first.size(); });
        return true;
    }
    // The compiled-in column for `code` (es, fr, de, pt); other codes: 0 entries.
    int loadBuiltin(const std::string& code)
    {
        const int c = column(code);
        if (c < 0) return 0;
        size_t n = 0;
        const Row* r = rows(n);
        int added = 0;
        for (size_t i = 0; i < n; ++i) {
            const char* t = c == 0 ? r[i].es : c == 1 ? r[i].fr : c == 2 ? r[i].de : r[i].pt;
            if (t && *t && add(r[i].en, t)) ++added;
        }
        return added;
    }
    // A lang/<code>.txt file: "English<TAB>Translation" per line, '#' comment lines, UTF-8 (a BOM is skipped).
    // Lines without a tab, empty sides or over kTextMax are skipped; at most kEntryMax entries.
    int loadText(const std::string& text)
    {
        size_t i = text.compare(0, 3, "\xef\xbb\xbf") == 0 ? 3 : 0;
        int added = 0;
        while (i < text.size() && size_t(added) < kEntryMax) {
            size_t e = text.find('\n', i);
            if (e == std::string::npos) e = text.size();
            std::string line = text.substr(i, e - i);
            i = e + 1;
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (line.empty() || line[0] == '#') continue;
            const size_t tab = line.find('\t');
            if (tab == std::string::npos) continue;
            const std::string en = line.substr(0, tab), tr = line.substr(tab + 1);
            if (en.size() > kTextMax || tr.size() > kTextMax || tr.find('\t') != std::string::npos) continue;
            if (add(en, tr)) ++added;
        }
        return added;
    }
    const std::string* exact(const std::string& s) const
    {
        const auto it = exact_.find(s);
        return it == exact_.end() ? nullptr : &it->second;
    }
    // The longest prefix entry that leaves something after it: out = its translation + the rest.
    bool prefixed(const std::string& s, std::string& out) const
    {
        for (const auto& p : prefixes_)
            if (s.size() > p.first.size() && s.compare(0, p.first.size(), p.first) == 0) {
                out.assign(p.second);
                out.append(s, p.first.size(), std::string::npos);
                return true;
            }
        return false;
    }
    std::string tr(const std::string& s) const
    {
        if (const std::string* t = exact(s)) return *t;
        std::string out;
        return prefixed(s, out) ? out : s;
    }

private:
    std::unordered_map<std::string, std::string> exact_;
    std::vector<std::pair<std::string, std::string>> prefixes_;   // longest first
};

} // namespace OmniUiLang
namespace OL10 = OmniUiLang;
'''

SHELL = r'''// OMNI_UI_LANG_V1: the shell side of Omni's UI language (pure part: OmniUiLang.h; reasons: tools/apply_ui_lang.py).
// omniTr(text) is applied where text is drawn (hint bar, toast, controller panels), never to stored texts.
// Language: /data/omni/ui-lang.txt ("auto" or a code), Automatic = the PS5 system language, resolved at run time
// (sceSystemServiceParamGetInt is not in the title's imports: dlopen/dlsym, like OmniMain.cpp's LoadExec).
// Overrides and extra languages: /data/omni/lang/<code>.txt ("English<TAB>Translation" lines).
#pragma once
#include "OmniUiLang.h"
#include <dlfcn.h>
#include <cstdio>
#include <string>

static OL10::Table omniUlTable;
static std::string omniUlChoice = "auto", omniUlCode = "en";   // the saved choice, the language in use
static bool omniUlLoaded = false;
static int omniUlSystem = -2;                                   // -2: not asked yet, -1: unavailable

static std::string omniUlRead(const std::string& path, size_t cap)
{
    std::string s;
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return s;
    char b[4096];
    size_t n;
    while (s.size() < cap && (n = fread(b, 1, sizeof(b), f)) > 0) s.append(b, std::min(n, cap - s.size()));
    fclose(f);
    return s;
}
static int omniUlSystemLang()
{
    if (omniUlSystem != -2) return omniUlSystem;
    omniUlSystem = -1;
    using ParamGetInt = int (*)(int, int*);
    ParamGetInt fn = nullptr;
    if (void* module = dlopen("libSceSystemService.sprx", RTLD_LAZY)) fn = reinterpret_cast<ParamGetInt>(dlsym(module, "sceSystemServiceParamGetInt"));
    if (!fn) fn = reinterpret_cast<ParamGetInt>(dlsym(RTLD_DEFAULT, "sceSystemServiceParamGetInt"));
    int v = -1;
    const int rc = fn ? fn(OL10::kParamLang, &v) : -1;
    if (fn && rc == 0 && v >= 0) omniUlSystem = v;
    fprintf(stderr, "ui-lang: system language %d (%s, rc %d)\n", omniUlSystem, fn ? "ParamGetInt" : "ParamGetInt not found", rc);
    return omniUlSystem;
}
// Loads the language: `choice` empty = read the saved one.
static void omniUlLoad(const std::string& choice = std::string())
{
    omniUlLoaded = true;
    omniUlChoice = choice.empty() ? OL10::parseChoice(omniUlRead("/data/omni/ui-lang.txt", 256)) : choice;
    omniUlCode = omniUlChoice == "auto" ? OL10::fromSystem(omniUlSystemLang()) : omniUlChoice;
    omniUlTable.clear();
    int builtIn = 0, fromFile = 0;
    if (omniUlCode != "en") {
        builtIn = omniUlTable.loadBuiltin(omniUlCode);
        fromFile = omniUlTable.loadText(omniUlRead("/data/omni/lang/" + omniUlCode + ".txt", OL10::kFileMax));
    }
    fprintf(stderr, "ui-lang: %s (choice %s): %d built-in + %d from lang/%s.txt\n", omniUlCode.c_str(), omniUlChoice.c_str(), builtIn, fromFile, omniUlCode.c_str());
}
// The text to draw for `s`: its translation, or `s` itself. The result is only valid while `s` is (prefix results
// live in a small ring, enough for the texts of one draw call).
static const std::string& omniTr(const std::string& s)
{
    if (!omniUlLoaded) omniUlLoad();
    if (omniUlTable.empty() || s.empty()) return s;
    if (const std::string* t = omniUlTable.exact(s)) return *t;
    static std::string ring[16];
    static unsigned next = 0;
    std::string& slot = ring[next++ % 16];
    return omniUlTable.prefixed(s, slot) ? slot : s;
}
// Language row: value (translated when drawn: "Automatic") and detail (the language Automatic picked).
static std::string omniUlValue()
{
    if (!omniUlLoaded) omniUlLoad();
    if (omniUlChoice == "auto") return "Automatic";
    const char* name = OL10::nativeName(omniUlChoice);
    return name ? std::string(name) : omniUlChoice;
}
static std::string omniUlDetail()
{
    if (!omniUlLoaded) omniUlLoad();
    if (omniUlChoice != "auto") return std::string();
    const char* name = OL10::nativeName(omniUlCode);
    return name ? std::string(name) : omniUlCode;
}
static void omniUlStep(int dir)
{
    if (!omniUlLoaded) omniUlLoad();
    const std::string next = OL10::step(omniUlChoice, dir);
    if (FILE* f = fopen("/data/omni/ui-lang.txt", "w")) { fputs(next.c_str(), f); fputs("\n", f); fclose(f); }
    else fprintf(stderr, "ui-lang: cannot save /data/omni/ui-lang.txt (choice kept until Omni closes)\n");
    omniUlLoad(next);
}
// OMNI_UI_LANG_V1_R2: true when a translation table is in use (not English): every stage-2 layout change is gated on it.
static bool omniUlActive()
{
    if (!omniUlLoaded) omniUlLoad();
    return !omniUlTable.empty();
}
// A format key ("Page %d of %d ...") with two ints, translated. Safe: Table::add refuses a translation whose printf
// conversions differ from the key's, so the format always takes exactly (int, int).
static std::string omniUlFormat(const char* key, int a, int b)
{
    const std::string k(key);
    const std::string& f = omniTr(k);
    char buf[512];
#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wformat-nonliteral"
#endif
    snprintf(buf, sizeof(buf), f.c_str(), a, b);
#if defined(__clang__)
#pragma clang diagnostic pop
#endif
    return buf;
}
'''

SETTINGS_FUNCS = (
    'constexpr int omniUlRowId = %d; // OMNI_UI_LANG_V1: Browser settings > "Language" (OmniUiLangShell.h)\n'
    'static void omniUlSettingsRow(OmniFxPanel& p)\n'
    '{\n'
    '    OmniFxRow r; r.id = omniUlRowId; r.label = "Language"; r.value = omniUlValue(); r.detail = omniUlDetail(); r.stepper = true;\n'
    '    p.rows.push_back(r);\n'
    '}\n'
    'static bool omniUlSettingsInput(int b)\n'
    '{\n'
    '    const int dir = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT ? -1 : (b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT || b == SDL_CONTROLLER_BUTTON_A) ? 1 : 0;\n'
    '    if (!dir) return false;\n'
    '    omniUlStep(dir);\n'
    '    omniFxRefresh();\n'
    '    return true;\n'
    '}\n') % ROW_ID

# apply_ui_scale.py r4 rewrites the hint bar (omniUisHints, a zoomed width, a zoomed centre line): the hint edits
# have a second spelling for such a tree (ALT: exactly one spelling must be found).
NOTE_UIS = '    if (!note.empty() && room > 60) omniLabel(note, float(x), float(omniUisTextZoom != 1.0 ? omniUisZoomedY(height - bottom / 2) : height - bottom / 2), omniSmall, T.inkDim, 0, room); // OMNI_UI_SCALE_V1_R4\n'
NOTE_UIS_V1 = '    if (!note.empty() && room > 60) omniLabel(omniTr(note), float(x), float(omniUisTextZoom != 1.0 ? omniUisZoomedY(height - bottom / 2) : height - bottom / 2), omniSmall, T.inkDim, 0, room); // OMNI_UI_SCALE_V1_R4; OMNI_UI_LANG_V1\n'
UIS_WIDTH_LINE = '    [[maybe_unused]] const int width = omniUisTextZoom != 1.0 && !omniUisTextOnly ? OUIS::zoomedW(omniUisTextZoom) : ::width; // OMNI_UI_SCALE_V1_R4 (Normal: 1280)\n'
HINTS_HEAD_UIS = ('// The bar\'s background is drawn by the caller; `note` (dim) fills the space between the groups.\n'
                  'static void omniHints(const std::vector<OmniHint>& left, const std::vector<OmniHint>& right = {}, const std::string& note = "")\n'
                  '{\n'
                  '    if (omniUisHints(left, right, note)) return; // OMNI_UI_SCALE_V1_R4: drawn zoomed (omniUisHints draws this line again inside its zoom)\n'
                  '    const OmniTheme& T = omniTheme();\n' + UIS_WIDTH_LINE)


class ALT(tuple):
    """Alternative (old, new) spellings of one edit: exactly one old must be in the file (with / without apply_ui_scale.py)."""
    def __new__(cls, *pairs):
        return tuple.__new__(cls, pairs)


EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniCaptionStyle.h" // OMNI_CAPTION_STYLE_V1: caption look (::cue user sheet), captions.txt (pure)\n',
         '#include "OmniCaptionStyle.h" // OMNI_CAPTION_STYLE_V1: caption look (::cue user sheet), captions.txt (pure)\n'
         '#include "OmniUiLangShell.h" // OMNI_UI_LANG_V1: Omni\'s own UI in other languages (omniTr: drawing only)\n'),
        ('static int omniHintItemW(const OmniHint& h) { return omniHintGlyphW(h.glyph) + 6 + int(omniTextWidthPx(omniSmall, h.label) / displayScale + 0.5); }\n',
         'static int omniHintItemW(const OmniHint& h) { return omniHintGlyphW(h.glyph) + 6 + int(omniTextWidthPx(omniSmall, omniTr(h.label)) / displayScale + 0.5); } // OMNI_UI_LANG_V1\n'),
        ('    omniLabel(h.label, float(x + omniHintGlyphW(h.glyph) + 6), float(cy), omniSmall, T.ink);\n',
         '    omniLabel(omniTr(h.label), float(x + omniHintGlyphW(h.glyph) + 6), float(cy), omniSmall, T.ink); // OMNI_UI_LANG_V1\n'),
        ALT(('    if (!note.empty() && room > 60) omniLabel(note, float(x), float(height - bottom / 2), omniSmall, T.inkDim, 0, room);\n',
             '    if (!note.empty() && room > 60) omniLabel(omniTr(note), float(x), float(height - bottom / 2), omniSmall, T.inkDim, 0, room); // OMNI_UI_LANG_V1\n'),
            (NOTE_UIS, NOTE_UIS_V1)),   # after apply_ui_scale.py r4 (its zoomed centre line)
        ('    const std::string shown = omniFit(omniSmall, message, physical(940));\n',
         '    const std::string shown = omniFit(omniSmall, omniTr(message), physical(940)); // OMNI_UI_LANG_V1: drawn translated, compared in English\n'),
    ],
    'OmniFeaturesPanel.h': [
        ('    const int cornerW = p.corner.empty() ? 0 : omniLabel(p.corner, g.x + g.w - 28, g.y + 34, omniSmall, T.inkFaint, 2);\n',
         '    const int cornerW = p.corner.empty() ? 0 : omniLabel(omniTr(p.corner), g.x + g.w - 28, g.y + 34, omniSmall, T.inkFaint, 2); // OMNI_UI_LANG_V1\n'),
        ('    omniLabel(p.title, g.x + 28, g.y + 34, omniBodyBold, T.ink, 0, g.w - 70 - cornerW);\n',
         '    omniLabel(omniTr(p.title), g.x + 28, g.y + 34, omniBodyBold, T.ink, 0, g.w - 70 - cornerW); // OMNI_UI_LANG_V1\n'),
        ('    if (!p.subtitle.empty()) omniLabel(p.subtitle, g.x + 28, g.y + 64, omniSmall, T.inkDim, 0, g.w - 56);\n',
         '    if (!p.subtitle.empty()) omniLabel(omniTr(p.subtitle), g.x + 28, g.y + 64, omniSmall, T.inkDim, 0, g.w - 56); // OMNI_UI_LANG_V1\n'),
        ('            const int vw = r.value.empty() ? 0 : omniLabel(r.value, tx + tw - 14, cy, omniSmall, side, 2, tw / 3);\n',
         '            const int vw = r.value.empty() ? 0 : omniLabel(omniTr(r.value), tx + tw - 14, cy, omniSmall, side, 2, tw / 3); // OMNI_UI_LANG_V1\n'),
        ('            omniHcLabel(r.label, tx + 46, cy, omniBody, ink, on, tw - 60 - vw); // OMNI_HIGH_CONTRAST_V1: disabled: struck, "(off)"\n',
         '            omniHcLabel(omniTr(r.label), tx + 46, cy, omniBody, ink, on, tw - 60 - vw); // OMNI_HIGH_CONTRAST_V1: disabled: struck, "(off)"; OMNI_UI_LANG_V1\n'),
        ('            if (!r.prefix.empty()) lx += omniLabel(r.prefix, lx, cy, omniSmall, side, 0, (g.x + g.w - 32 - lx) / 4) + 12; // OMNI_SETTINGS_SEARCH_V1: the section, dim\n',
         '            if (!r.prefix.empty()) lx += omniLabel(omniTr(r.prefix), lx, cy, omniSmall, side, 0, (g.x + g.w - 32 - lx) / 4) + 12; // OMNI_SETTINGS_SEARCH_V1: the section, dim; OMNI_UI_LANG_V1\n'),
        ('                omniLabel(r.value, g.x + g.w - 118, cy, omniBodyBold, sel && on ? T.accentInk : T.ink, 1, 130);\n',
         '                omniLabel(omniTr(r.value), g.x + g.w - 118, cy, omniBodyBold, sel && on ? T.accentInk : T.ink, 1, 130); // OMNI_UI_LANG_V1\n'),
        ('            } else if (!r.value.empty()) right = omniLabel(r.value, g.x + g.w - 32, cy, omniSmall, side, 2, g.w / 3) + 18;\n',
         '            } else if (!r.value.empty()) right = omniLabel(omniTr(r.value), g.x + g.w - 32, cy, omniSmall, side, 2, g.w / 3) + 18; // OMNI_UI_LANG_V1\n'),
        ('            const int lw = omniHcLabel(r.label, lx, cy, omniBody, ink, on, r.detail.empty() ? room : std::min(room, room * 3 / 5)); // OMNI_HIGH_CONTRAST_V1\n',
         '            const int lw = omniHcLabel(omniTr(r.label), lx, cy, omniBody, ink, on, r.detail.empty() ? room : std::min(room, room * 3 / 5)); // OMNI_HIGH_CONTRAST_V1; OMNI_UI_LANG_V1\n'),
        ('            if (!r.detail.empty() && room - lw > 40) omniLabel(r.detail, lx + lw + 14, cy, omniSmall, side, 0, room - lw - 14);\n',
         '            if (!r.detail.empty() && room - lw > 40) omniLabel(omniTr(r.detail), lx + lw + 14, cy, omniSmall, side, 0, room - lw - 14); // OMNI_UI_LANG_V1\n'),
    ],
    'OmniBrowserSettings.h': [
        ('#include "OmniSettingsSearchShell.h" // OMNI_SETTINGS_SEARCH_V1: Search settings (omniSsrFilter, omniSsrPanelInput)\n',
         '#include "OmniSettingsSearchShell.h" // OMNI_SETTINGS_SEARCH_V1: Search settings (omniSsrFilter, omniSsrPanelInput)\n'
         + SETTINGS_FUNCS),
        ('    add(omniFxSetSearch, "Search engine", omniFxEngines[omniFxSet.search].name, true);\n',
         '    omniUlSettingsRow(p); // OMNI_UI_LANG_V1: Language (first: found without reading the rest)\n'
         '    add(omniFxSetSearch, "Search engine", omniFxEngines[omniFxSet.search].name, true);\n'),
        ('static bool omniFxSettingsInput(OmniFxPanel&, const OmniFxRow& r, int b)\n{\n',
         'static bool omniFxSettingsInput(OmniFxPanel&, const OmniFxRow& r, int b)\n{\n'
         '    if (r.id == omniUlRowId) return omniUlSettingsInput(b); // OMNI_UI_LANG_V1 (before the >= 300 rows)\n'),
    ],
}


# ---------------------------------------------------------------------------------------------------------------
# OMNI_UI_LANG_V1_R2 edits. They anchor on the tree AFTER the V1 edits (stage-1 lines included), so a stage-1 tree and
# a fresh tree (V1 applied in memory first) end the same.
# ---------------------------------------------------------------------------------------------------------------
OB_LITERALS = r'''// OMNI_UI_LANG_V1_R2: drawn text that is a const char* - a string literal, a ternary of literals, or one of the shell's
// constant tables (OCH::sectionTitle, OHCT::toggleWord, OOR::kBadge ...) - is Omni's own UI and is drawn translated;
// a std::string (page titles, addresses, host and file names, user words, anything built at run time) is drawn as it
// is. The compiler picks the overload below for exactly the const char* calls: no call site changes. Audited
// 2026-11-16 (the overload [[deprecated]], tree compiled): 62 sites, all UI text or arrows.
// Layout: a translated text wider than its maxW takes the next smaller face first, then omniFit's ellipsis.
// English (no table) keeps its face and width.
static int omniUlSmaller(int face)
{
    switch (face) {
    case omniBody: return omniSmall;
    case omniSmall: return omniCaption;
    case omniBodyBold: return omniSmallBold;
    case omniSmallBold: return omniCaptionBold;
    case omniTitle: return omniBodyBold;
    default: return face;
    }
}
static int omniUlFace(int face, const std::string& shown, int maxW)
{
    if (maxW <= 0 || !omniUlActive() || omniTextWidthPx(face, shown) <= physical(maxW)) return face;
    const int smaller = omniUlSmaller(face);
    return smaller != face && omniFaces[smaller].f ? smaller : face;
}
static int omniLabel(const char* value, float x, float cy, int id, SDL_Color color, int align = 0, int maxW = 0, uint8_t alpha = 255)
{
    if (!value || !*value) return 0;
    const std::string en(value);
    const std::string& shown = omniTr(en);
    return omniLabel(shown, x, cy, &shown == &en ? id : omniUlFace(id, shown, maxW), color, align, maxW, alpha);
}
// The hint bar's label face and width cap: omniUlHintFit sets them for one bar (translated and too wide), omniHints
// puts them back after it. English: never changed.
static int omniUlHintFace = omniSmall, omniUlHintMax = 0;
static std::string omniUlHintText(const std::string& label)
{
    const std::string& t = omniTr(label);
    return omniUlHintMax > 0 ? omniFit(omniUlHintFace, t, physical(omniUlHintMax)) : t;
}

'''

OB_HINTFIT = r'''// OMNI_UI_LANG_V1_R2: a translated bar wider than the screen: labels take the Caption face; still too wide: every
// label is cut to one shared cap (OL10::fitCap, ellipsis). omniHintItemW / omniHintDraw use the same face and cap.
static void omniUlHintFit(const std::vector<OmniHint>& left, const std::vector<OmniHint>& right, int barW)   // barW: the line's layout width
{
    omniUlHintFace = omniSmall; omniUlHintMax = 0;
    const size_t n = left.size() + right.size();
    if (!n || !omniUlActive()) return;
    const int room = barW - 40 - omniHintGap * int(n - 1);
    auto need = [&] { int w = 0; for (const auto* g : { &left, &right }) for (const auto& h : *g) w += omniHintItemW(h); return w; };
    if (need() <= room) return;
    if (omniFaces[omniCaption].f) omniUlHintFace = omniCaption;
    if (need() <= room) return;
    std::vector<int> labels;
    int fixed = 0;
    for (const auto* g : { &left, &right })
        for (const auto& h : *g) {
            labels.push_back(int(omniTextWidthPx(omniUlHintFace, omniTr(h.label)) / displayScale + 0.5));
            fixed += omniHintGlyphW(h.glyph) + 6;
        }
    omniUlHintMax = OL10::fitCap(labels, room - fixed);
}
'''

SSR_VIEW = r'''// OMNI_UI_LANG_V1_R2: with the UI in another language a row matches by its English label / value / section (as
// before) or by the ones the user sees (translated; case and accents folded on both sides: "configuracion" finds
// "Configuración"). The better tier of the two orders it; OSSR::view's "rows already shown stay put" rule is kept.
static std::vector<size_t> omniUlSsrView(const std::vector<OSSR::Entry>& list, const std::string& query, std::vector<int>& shown)
{
    if (!omniUlActive() || OSSR::norm(query).empty()) return OSSR::view(list, query, shown);
    const std::string nq = OSSR::norm(query), fq = OSSR::norm(OL10::fold(query));
    const std::vector<std::string> syn = OSSR::synonymPhrases(nq), fsyn = OSSR::synonymPhrases(fq);
    std::vector<int> en, tr, ids;
    for (const auto& e : list) {
        en.push_back(int(OSSR::tierOf(e, nq, syn)));
        OSSR::Entry t;
        t.id = e.id; t.section = OL10::fold(omniTr(e.section)); t.label = OL10::fold(omniTr(e.label)); t.value = OL10::fold(omniTr(e.value));
        tr.push_back(int(OSSR::tierOf(t, fq, fsyn)));
        ids.push_back(e.id);
    }
    return OL10::keepShown(OL10::bestOf(en, tr, int(OSSR::NoMatch)), ids, shown);
}
'''

R2 = '; OMNI_UI_LANG_V1_R2'
EDITS2 = {
    'OmniBrowser.cpp': [
        ('// OMNI_VIDEO_IMMERSIVE_V1: a playing video covers most of the page view (a site\'s own "fullscreen" player).\n',
         OB_LITERALS + '// OMNI_VIDEO_IMMERSIVE_V1: a playing video covers most of the page view (a site\'s own "fullscreen" player).\n'),
        ('static int omniHintItemW(const OmniHint& h) { return omniHintGlyphW(h.glyph) + 6 + int(omniTextWidthPx(omniSmall, omniTr(h.label)) / displayScale + 0.5); } // OMNI_UI_LANG_V1\n',
         'static int omniHintItemW(const OmniHint& h) { return omniHintGlyphW(h.glyph) + 6 + int(omniTextWidthPx(omniUlHintFace, omniUlHintText(h.label)) / displayScale + 0.5); } // OMNI_UI_LANG_V1' + R2 + ': face / cap of omniUlHintFit\n'),
        ('    omniLabel(omniTr(h.label), float(x + omniHintGlyphW(h.glyph) + 6), float(cy), omniSmall, T.ink); // OMNI_UI_LANG_V1\n',
         '    omniLabel(omniUlHintText(h.label), float(x + omniHintGlyphW(h.glyph) + 6), float(cy), omniUlHintFace, T.ink); // OMNI_UI_LANG_V1' + R2 + '\n'),
        ALT(('// The bar\'s background is drawn by the caller; `note` (dim) fills the space between the groups.\n'
         'static void omniHints(const std::vector<OmniHint>& left, const std::vector<OmniHint>& right = {}, const std::string& note = "")\n'
         '{\n'
         '    const OmniTheme& T = omniTheme();\n',
         OB_HINTFIT +
         '// The bar\'s background is drawn by the caller; `note` (dim) fills the space between the groups.\n'
         'static void omniHints(const std::vector<OmniHint>& left, const std::vector<OmniHint>& right = {}, const std::string& note = "")\n'
         '{\n'
         '    const OmniTheme& T = omniTheme();\n'
         '    omniUlHintFit(left, right, width); // OMNI_UI_LANG_V1_R2: a translated bar that does not fit: smaller face, then shorter labels\n'),
            (HINTS_HEAD_UIS, OB_HINTFIT + HINTS_HEAD_UIS + '    omniUlHintFit(left, right, width); // OMNI_UI_LANG_V1_R2: a translated bar that does not fit: smaller face, then shorter labels\n')),
        ALT(('    if (!note.empty() && room > 60) omniLabel(omniTr(note), float(x), float(height - bottom / 2), omniSmall, T.inkDim, 0, room); // OMNI_UI_LANG_V1\n',
         '    if (!note.empty() && room > 60) omniLabel(omniTr(note), float(x), float(height - bottom / 2), omniSmall, T.inkDim, 0, room); // OMNI_UI_LANG_V1\n'
         '    omniUlHintFace = omniSmall; omniUlHintMax = 0; // OMNI_UI_LANG_V1_R2: the next bar starts from the normal face\n'),
            (NOTE_UIS_V1, NOTE_UIS_V1 + '    omniUlHintFace = omniSmall; omniUlHintMax = 0; // OMNI_UI_LANG_V1_R2: the next bar starts from the normal face\n')),
        ('    auto label = [&](const std::string& s) { x += omniLabel(s, float(x), float(y), omniSmall, T.ink) + 16; };\n',
         '    auto label = [&](const std::string& s) { const bool tl = omniUlActive(); x += omniLabel(omniTr(s), float(x), float(y), tl ? omniCaption : omniSmall, T.ink, 0, tl ? std::max(1, width - 18 - x) : 0) + 16; }; // OMNI_UI_LANG_V1_R2: translated: Caption face, stops at the screen edge\n'),
        ('            const int ww = int(omniTextWidthPx(omniCaptionBold, word) / displayScale + 0.5), x0 = 1153 - (ww + 13) / 2;\n',
         '            const int ww = int(omniTextWidthPx(omniCaptionBold, omniTr(word)) / displayScale + 0.5), x0 = 1153 - (ww + 13) / 2; // OMNI_UI_LANG_V1_R2: measured as drawn\n'),
        ('        const int tw = int(omniTextWidthPx(omniCaption, tip) / displayScale + 0.5);\n',
         '        const int tw = int(omniTextWidthPx(omniCaption, omniTr(tip)) / displayScale + 0.5); // OMNI_UI_LANG_V1_R2: measured as drawn\n'),
    ],
    'OmniFeaturesPanel.h': [
        ('            const int vw = r.value.empty() ? 0 : omniLabel(omniTr(r.value), tx + tw - 14, cy, omniSmall, side, 2, tw / 3); // OMNI_UI_LANG_V1\n',
         '            const int vw = r.value.empty() ? 0 : omniLabel(omniTr(r.value), tx + tw - 14, cy, omniUlFace(omniSmall, omniTr(r.value), tw / 3), side, 2, tw / 3); // OMNI_UI_LANG_V1' + R2 + ': shrink to fit\n'),
        ('            omniHcLabel(omniTr(r.label), tx + 46, cy, omniBody, ink, on, tw - 60 - vw); // OMNI_HIGH_CONTRAST_V1: disabled: struck, "(off)"; OMNI_UI_LANG_V1\n',
         '            omniHcLabel(omniTr(r.label), tx + 46, cy, omniUlFace(omniBody, omniTr(r.label), tw - 60 - vw), ink, on, tw - 60 - vw); // OMNI_HIGH_CONTRAST_V1: disabled: struck, "(off)"; OMNI_UI_LANG_V1' + R2 + '\n'),
        ('                omniLabel(omniTr(r.value), g.x + g.w - 118, cy, omniBodyBold, sel && on ? T.accentInk : T.ink, 1, 130); // OMNI_UI_LANG_V1\n',
         '                omniLabel(omniTr(r.value), g.x + g.w - 118, cy, omniUlFace(omniBodyBold, omniTr(r.value), 130), sel && on ? T.accentInk : T.ink, 1, 130); // OMNI_UI_LANG_V1' + R2 + '\n'),
        ('            } else if (!r.value.empty()) right = omniLabel(omniTr(r.value), g.x + g.w - 32, cy, omniSmall, side, 2, g.w / 3) + 18; // OMNI_UI_LANG_V1\n',
         '            } else if (!r.value.empty()) right = omniLabel(omniTr(r.value), g.x + g.w - 32, cy, omniUlFace(omniSmall, omniTr(r.value), g.w / 3), side, 2, g.w / 3) + 18; // OMNI_UI_LANG_V1' + R2 + '\n'),
        ('            const int lw = omniHcLabel(omniTr(r.label), lx, cy, omniBody, ink, on, r.detail.empty() ? room : std::min(room, room * 3 / 5)); // OMNI_HIGH_CONTRAST_V1; OMNI_UI_LANG_V1\n',
         '            const int lw = omniHcLabel(omniTr(r.label), lx, cy, omniUlFace(omniBody, omniTr(r.label), r.detail.empty() ? room : std::min(room, room * 3 / 5)), ink, on, r.detail.empty() ? room : std::min(room, room * 3 / 5)); // OMNI_HIGH_CONTRAST_V1; OMNI_UI_LANG_V1' + R2 + '\n'),
    ],
    'OmniControlsHelpShell.h': [
        ('    if (e.hold) x += omniChPill("Hold", x, cy) + 6;\n',
         '    if (e.hold) x += omniChPill(omniTr("Hold"), x, cy) + 6; // OMNI_UI_LANG_V1_R2\n'),
        ('    omniLabel(OCH::expand(OCH::sectionWhere(section), ps), width - OCH::kMarginX, OCH::kTitleY, omniSmall, T.inkDim, 2, 700);\n',
         '    omniLabel(OCH::expand(omniTr(OCH::sectionWhere(section)), ps), width - OCH::kMarginX, OCH::kTitleY, omniSmall, T.inkDim, 2, 700); // OMNI_UI_LANG_V1_R2: translated before the {tokens} expand\n'),
        ('        std::string act = OCH::expand(e.action, ps), note = OCH::expand(e.note, ps);\n',
         '        std::string act = OCH::expand(omniTr(e.action), ps), note = OCH::expand(omniTr(e.note), ps); // OMNI_UI_LANG_V1_R2: translated before the {tokens} expand\n'),
        ('        if (omniChRemap && omniChRemap(e.action, e.where, ra, rn)) { act = OCH::expand(ra, ps); note = OCH::expand(rn, ps); }   // remapped button\n',
         '        if (omniChRemap && omniChRemap(e.action, e.where, ra, rn)) { act = OCH::expand(omniTr(ra), ps); note = OCH::expand(omniTr(rn), ps); }   // remapped button; OMNI_UI_LANG_V1_R2\n'),
        ('        if (note.empty()) omniLabel(act, float(tx), cy, omniBody, T.ink, 0, room);\n',
         '        if (note.empty()) omniLabel(act, float(tx), cy, omniUlFace(omniBody, act, room), T.ink, 0, room); // OMNI_UI_LANG_V1_R2: shrink to fit\n'),
        ('            omniLabel(act, float(tx), cy - 9, omniBody, T.ink, 0, room);\n',
         '            omniLabel(act, float(tx), cy - 9, omniUlFace(omniBody, act, room), T.ink, 0, room); // OMNI_UI_LANG_V1_R2: shrink to fit\n'),
        ('    if (L.pages > 1) more = "Page " + std::to_string(omniChPage + 1) + " of " + std::to_string(L.pages) + "   D-pad \\xe2\\x96\\xb2 \\xe2\\x96\\xbc more";\n',
         '    if (L.pages > 1) more = omniUlFormat("Page %d of %d   D-pad \\xe2\\x96\\xb2 \\xe2\\x96\\xbc more", omniChPage + 1, L.pages); // OMNI_UI_LANG_V1_R2: same English text, translatable\n'),
    ],
    'OmniSettingsSearchShell.h': [
        ('static OmniFxRow omniSsrSearchRow()\n',
         SSR_VIEW + 'static OmniFxRow omniSsrSearchRow()\n'),
        ('    const std::vector<size_t> pick = OSSR::view(list, omniSsrQuery, omniSsrShown);\n',
         '    const std::vector<size_t> pick = omniUlSsrView(list, omniSsrQuery, omniSsrShown); // OMNI_UI_LANG_V1_R2: English or translated label\n'),
    ],
    'OmniDlProgressShell.h': [
        ('        offTextW = float(omniTextWidthPx(omniCaptionBold, OOR::kBadge) / displayScale);\n',
         '        offTextW = float(omniTextWidthPx(omniCaptionBold, omniTr(OOR::kBadge)) / displayScale); // OMNI_UI_LANG_V1_R2: measured as drawn\n'),
    ],
    'OmniOfflineRetryShell.h': [
        ('    const float textW = float(omniTextWidthPx(omniCaptionBold, OOR::kBadge) / displayScale);\n',
         '    const float textW = float(omniTextWidthPx(omniCaptionBold, omniTr(OOR::kBadge)) / displayScale); // OMNI_UI_LANG_V1_R2: measured as drawn\n'),
    ],
}
EDITS2['OmniUiScalePanels.h'] = [   # apply_ui_scale.py r4: the hint line's natural width measures the note as drawn
    ('    if (!note.empty()) natural += int(omniTextWidthPx(omniSmall, note) / displayScale + 0.5) + (right.empty() ? omniHintGap : 0);\n',
     '    if (!note.empty()) natural += int(omniTextWidthPx(omniSmall, omniTr(note)) / displayScale + 0.5) + (right.empty() ? omniHintGap : 0); // OMNI_UI_LANG_V1_R2: as drawn\n'),
]
OPTIONAL2 = ('OmniDlProgressShell.h', 'OmniOfflineRetryShell.h', 'OmniUiScalePanels.h')   # skipped when the file is not in the tree
# Lines only a tree with apply_ui_scale.py r4 has (applied when found once): its Protection pill cap measures the word.
UIS_CAP = '        OmniUisTextCap uisCap(usable ? omniCaptionBold : omniCaption, !usable ? "Protection" : trusted ? "Allowed" : "Protected", usable ? 78 : 88); // OMNI_UI_SCALE_V1_R4: the word fits the 98 px pill\n'
OPTIONAL_LINES2 = {'OmniBrowser.cpp': [(UIS_CAP, UIS_CAP.replace('!usable ? "Protection" : trusted ? "Allowed" : "Protected", usable', 'omniTr(!usable ? "Protection" : trusted ? "Allowed" : "Protected"), usable').replace('\n', '; OMNI_UI_LANG_V1_R2: the translated word\n'))]}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def ids_free():
    """Refuse if the row id / alias / names are taken by another patch already in the tree."""
    if MARK in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):   # OMNI_RERUN_SAFE: already applied; later patches use omniTr( on purpose
        return
    for f in sorted(root.iterdir()):
        if f.suffix not in ('.h', '.cpp', '.inc') or '.pre-' in f.name or f.name.startswith('OmniUiLang'):
            continue
        s = f.read_bytes().decode('utf-8', 'replace')
        if MARK in s:
            continue
        s = cpp_code(s)
        names = () if f.name in GUIDE else ('namespace OL10', 'omniUlRowId', 'omniTr(', 'omniUlFace(', 'omniUlSsrView',
                                            'omniUlHintFit', 'omniUlFormat')
        for word in (' = %d;' % ROW_ID, '= %d,' % ROW_ID) + names:
            if word in s:
                sys.exit('%s: %r is already used: pick another id / alias' % (f.name, word))


def apply_edits(name, s, edits):
    """The edits on text s in memory; every anchor must be found exactly once (in the file's own line endings)."""
    for edit in edits:
        pairs = list(edit) if isinstance(edit, ALT) else [edit]
        hits = [(variants(o, s), n) for o, n in pairs]
        hits = [(oe, n) for oe, n in hits if s.count(oe[0]) == 1]
        if len(hits) != 1:
            sys.exit('%s: anchor found %d times (spellings matching: %d of %d): %r'
                     % (name, s.count(variants(pairs[0][0], s)[0]), len(hits), len(pairs), pairs[0][0][:100]))
        (old, e), new0 = hits[0]
        s = s.replace(old, new0.replace('\n', e), 1)
    return s


def main():
    for need, mark in (('OmniFeaturesPanel.h', 'OMNI_SETTINGS_SEARCH_V1'), ('OmniFeaturesPanel.h', 'OMNI_HIGH_CONTRAST_V1'),
                       ('OmniBrowserSettings.h', 'OMNI_SETTINGS_SEARCH_V1'), ('OmniBrowser.cpp', 'OMNI_CAPTION_STYLE_V1'),
                       ('OmniControlsHelpShell.h', 'OMNI_CONTROLS_HELP_V1'), ('OmniSettingsSearchShell.h', 'OMNI_SETTINGS_SEARCH_V1')):
        if not (root / need).exists() or mark not in (root / need).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: apply the recipe up to apply_ublock_refine.py (and apply_button_map.py) first' % (need, mark))
    ids_free()
    # Every file is computed in memory first (V1 where it is missing, then R2 where it is missing): a missing anchor
    # stops the script before anything is written.
    out = []
    for name in list(EDITS) + [n for n in EDITS2 if n not in EDITS]:
        p = root / name
        if not p.exists():
            if name in OPTIONAL2:
                continue
            sys.exit('%s: missing' % name)
        orig = p.read_bytes().decode('utf-8')
        s = orig
        if name in EDITS and MARK not in s:
            s = apply_edits(name, s, EDITS[name])
        if name in EDITS2 and MARK2 not in s:
            s = apply_edits(name, s, EDITS2[name])
            for old0, new0 in OPTIONAL_LINES2.get(name, []):   # lines only some trees have (apply_ui_scale.py r4)
                old, e = variants(old0, s)
                if s.count(old) == 1:
                    s = s.replace(old, new0.replace('\n', e), 1)
        out.append((name, p, orig, s))
    msgs = [write_new('OmniUiLang.h', PURE.replace('@TABLE@', table_cpp()), 'OmniCaptionStyle.h'),
            write_new('OmniUiLangShell.h', SHELL, 'OmniCaptionStyle.h')]
    for name, p, orig, s in out:
        if s == orig:
            msgs.append(name + ': already')
        else:
            p.write_bytes(s.encode('utf-8'))
            msgs.append(name + ': applied')
    for m in msgs:
        print(m)
    en_only = sum(1 for r in TABLE if r[1] is None)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK2
          + ' (%d strings: %d translated, %d English-only; %d unsure)'
          % (len(TABLE), len(TABLE) - en_only, en_only, sum(1 for r in TABLE if r[5])))


main()
