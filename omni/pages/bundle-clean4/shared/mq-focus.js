// SPDX-License-Identifier: GPL-3.0-or-later
(()=>{'use strict';if(document.body.classList.contains('mq-start'))return;
document.addEventListener('focusin',e=>{const target=e.target;if(target.matches('button,a,select,input')){document.querySelectorAll('.pad-focus').forEach(x=>x.classList.remove('pad-focus'));target.classList.add('pad-focus')}requestAnimationFrame(()=>{if(document.activeElement!==target||target.closest('dialog'))return;const footer=document.querySelector('.hintbar'),rect=target.getBoundingClientRect(),edge=footer?footer.getBoundingClientRect().top:innerHeight;if(rect.bottom+12>edge)scrollBy(0,rect.bottom+12-edge);else if(rect.top<12)scrollBy(0,rect.top-12)})});
})();
