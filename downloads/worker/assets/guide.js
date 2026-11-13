/* Omnibloom quick guide for the original Universes. No networking, persistence, or automatic popups. */
(() => {
  'use strict';
  if (document.getElementById('guide-dialog') || document.getElementById('help-toggle')) return;
  const footer = document.querySelector('.app-footer');
  if (!footer) return;

  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const icon = (name) => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'icon');
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', '/assets/icons.svg#' + name);
    svg.append(use);
    return svg;
  };
  const paragraph = (text, className) => make('p', text, className);
  const section = (heading, id) => {
    const node = make('section', undefined, 'guide-section');
    const title = make('h3', heading);
    title.id = id;
    node.setAttribute('aria-labelledby', id);
    node.append(title);
    return node;
  };

  const navigation = Object.freeze({
    bloom: {
      name: 'Bloom', lead: 'Five destinations unfold from one living mark.',
      steps: ['Choose a numbered petal to open that page.', 'Use the arrow keys or the D-pad to move between petals, then Enter or the confirm button to open one.']
    },
    relay: {
      name: 'Relay', lead: 'Make the next connection.',
      steps: ['Choose a socket on the signal board to open its page.', 'Use the arrow keys or the D-pad to move between sockets, then Enter or the confirm button to connect.']
    },
    loom: {
      name: 'Loom', lead: 'Pull the right thread.',
      steps: ['Each woven strand is one of your five pages.', 'Use the arrow keys or the D-pad to move between strands, then Enter or the confirm button to pull one forward.']
    },
    kinetic: {
      name: 'Kinetic', lead: 'Find your balance.',
      steps: ['Each hanging weight opens one of your five pages.', 'Use the arrow keys or the D-pad to move between weights, then Enter or the confirm button to set one in motion.']
    },
    tide: {
      name: 'Tide', lead: 'Catch the next current.',
      steps: ['Each band of the tide table opens one of your five pages.', 'Use the arrow keys or the D-pad to move between currents, then Enter or the confirm button to ride one.']
    },
    aurora: {
      name: 'Aurora', lead: 'A calm glass rail. Everything stays in reach.',
      steps: ['Choose a labeled destination in the glass sidebar.', 'The highlighted card marks your current page. Use Tab to reach a destination and Enter to open it.']
    },
    cosmic: {
      name: 'Cosmic', lead: 'Choose a planet. Find a new space.',
      steps: ['Each labeled planet opens one of your five pages.', 'Use Tab to move through the planets, then Enter to open the focused destination. No dragging is needed.']
    },
    arcade: {
      name: 'Arcade', lead: 'Choose your level. Press play.',
      steps: ['Use the direction pad or arrow keys while navigation is focused to preview a destination.', 'Press the A control or Enter to open the selected page. On smaller screens, choose a labeled destination in the compact menu.']
    },
    solstice: {
      name: 'Solstice', lead: 'Your next chapter is one card away.',
      steps: ['Choose a numbered destination card in the horizontal ribbon.', 'On a narrow screen, scroll the ribbon sideways to reveal the remaining cards. Tab and Enter work too.']
    },
    metro: {
      name: 'Metro', lead: 'Five stops. Your route to everything.',
      steps: ['Choose any labeled station to open its page.', 'Use the next-station arrow to continue along the line. The marked station shows where you are.']
    },
    sakura: {
      name: 'Sakura', lead: 'Turn a page. Keep a good find.',
      steps: ['Choose a chapter in the book index to open that page.', 'The previous and next chapter buttons turn pages. Page Up and Page Down also work when you are not typing.']
    },
    abyss: {
      name: 'Abyss', lead: 'A little deeper. A new destination.',
      steps: ['Choose a labeled depth to open its page.', 'The Dive control slider is another way to choose a destination. Its depth marks describe navigation, not download progress or storage.']
    },
    prism: {
      name: 'Prism', lead: 'Type a destination. Make your way.',
      steps: ['Type a page name in the destination search to narrow the list.', 'Choose a result, or press Enter in the search to open its first result.', 'Press / or Ctrl/Cmd + K when you are not typing to focus this search. Escape in the search clears it.']
    },
    atlas: {
      name: 'Atlas', lead: 'One place for each part of your day.',
      steps: ['Choose a large labeled tile to open that destination.', 'The highlighted tile marks the current page. Keyboard focus follows the same reading order as the tiles.']
    },
    cassette: {
      name: 'Cassette', lead: 'Find your track. Press play.',
      steps: ['Use previous and next to preview a destination, then press the deck play control to open it.', 'The seek slider and labeled track buttons also select destinations.', 'Deck controls navigate pages. Use the controls on a queue item to manage a worker job.']
    }
  });

  const currentNavigation = (id) => navigation[id] || navigation.bloom;

  const dialog = make('dialog');
  dialog.id = 'guide-dialog';
  dialog.setAttribute('aria-labelledby', 'guide-heading');
  dialog.setAttribute('aria-describedby', 'guide-description');
  const header = make('div', undefined, 'dialog-heading');
  const intro = make('div');
  intro.append(make('span', 'A LITTLE HELP ALONG THE WAY', 'eyebrow'));
  const heading = make('h2', 'Make yourself at home.');
  heading.id = 'guide-heading';
  const description = paragraph('A quick guide to your space, with tips for the universe you have chosen.');
  description.id = 'guide-description';
  intro.append(heading, description);
  const close = make('button', undefined, 'icon-button');
  close.id = 'guide-close';
  close.type = 'button';
  close.setAttribute('aria-label', 'Close quick guide');
  close.append(icon('close'));
  header.append(intro, close);
  dialog.append(header);

  const note = paragraph('The guide only explains navigation. Real downloads require explicit submission; Demo jobs save no media.', 'guide-preview-note');
  dialog.append(note);
  const current = section('Your universe', 'guide-navigation-heading');
  const mode = paragraph('', 'guide-current-mode');
  mode.id = 'guide-current-mode';
  const lead = paragraph('', 'guide-navigation-lead');
  lead.id = 'guide-navigation-lead';
  const steps = make('ol', undefined, 'guide-steps');
  steps.id = 'guide-navigation-steps';
  current.append(mode, lead, steps);
  dialog.append(current);

  const pages = section('Five familiar places', 'guide-pages-heading');
  const routes = make('dl', undefined, 'guide-route-list');
  [
    ['Launch', 'Add a link, choose an engine, or try a sample transfer.'],
    ['Queue', 'See reported worker status. Cancel active jobs or hold the waiting queue; a queue hold does not pause an active transfer.'],
    ['Saved links', 'Keep a URL for later. Saving a link does not start a transfer.'],
    ['Activity', 'Look back over the worker’s bounded job history.'],
    ['Settings', 'Choose preferences, including a calmer reduced-motion experience.']
  ].forEach(([name, text]) => {
    const row = make('div');
    row.append(make('dt', name), make('dd', text));
    routes.append(row);
  });
  pages.append(routes);
  dialog.append(pages);

  const engines = section('Two engines. Your choice.', 'guide-engines-heading');
  const engineGrid = make('div', undefined, 'guide-engine-grid');
  [
    ['yt-dlp', 'The video and audio option. Choose it before adding a media link.'],
    ['JDownloader', 'The files and links option. Choose it before adding a file link.']
  ].forEach(([name, text]) => {
    const card = make('div', undefined, 'guide-engine-card');
    card.append(make('h4', name), paragraph(text));
    engineGrid.append(card);
  });
  engines.append(engineGrid, paragraph('Availability comes from the authenticated worker. Choosing an engine never starts Java. Demo samples simulate progress without fetching or saving media.', 'guide-small-note'));
  dialog.append(engines);

  const footerNote = make('div', undefined, 'guide-dialog-footer');
  footerNote.append(paragraph('Change universe whenever you like. Your saved links and queue stay in place.'));
  const done = make('button', 'Got it. Let’s explore.', 'primary-button');
  done.type = 'button';
  done.id = 'guide-done';
  footerNote.append(done);
  dialog.append(footerNote);

  const button = make('button', undefined, 'text-button');
  button.id = 'help-toggle';
  button.type = 'button';
  button.setAttribute('aria-haspopup', 'dialog');
  button.setAttribute('aria-controls', 'guide-dialog');
  button.append(icon('info'), make('span', 'Quick guide'));
  const previewInfo = footer.querySelector('#preview-info');
  footer.insertBefore(button, previewInfo);
  document.body.append(dialog);

  let opener = null;
  const restoreFocus = () => {
    const target = opener;
    opener = null;
    if (document.querySelector('dialog[open]')) return;
    if (target instanceof HTMLElement && target.isConnected) target.focus({ preventScroll: true });
  };
  button.addEventListener('click', () => {
    if (document.querySelector('dialog[open]')) return;
    window.dispatchEvent(new CustomEvent('omni:overlay-open', {detail:{overlay:'quick-guide'}}));
    const chosen = currentNavigation(document.body.dataset.theme);
    mode.textContent = chosen.name;
    dialog.dataset.guideTheme = document.body.dataset.theme || 'bloom';
    lead.textContent = chosen.lead;
    steps.replaceChildren(...chosen.steps.map(text => make('li', text)));
    opener = document.activeElement;
    dialog.showModal();
    dialog.scrollTop = 0;
    close.focus({ preventScroll: true });
  });
  close.addEventListener('click', () => dialog.close());
  done.addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', restoreFocus);
  // Native dialog Escape handling closes this modal; the close event restores focus.
  // The app's shared dynamic dialog Tab trap handles focus containment. No shortcut
  // listener is installed here, so typing and existing navigation keys are untouched.
})();
