// SPDX-License-Identifier: GPL-3.0-or-later
// Presentation grouping only; original form/button handlers remain attached.
(()=>{'use strict';for(const [button,panel]of [['mq-addon-more','mq-addon-options'],['mq-password-more','mq-password-options']]){const b=document.getElementById(button),p=document.getElementById(panel);if(b&&p)b.addEventListener('click',()=>{p.hidden=!p.hidden;b.setAttribute('aria-expanded',String(!p.hidden))})}})();
