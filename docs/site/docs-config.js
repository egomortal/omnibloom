(function(root){'use strict';
const versions=Object.freeze({launch:'index.html',manual:'manual.html'});
function resolveTarget(target,base){if(typeof target!=='string'||!target.trim())throw Error('Documentation target is empty');const url=new URL(target,base),origin=new URL(base);if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.protocol==='http:'&&url.origin!==origin.origin)throw Error('Documentation target must be same-origin HTTP(S) or public HTTPS');return url.href;}
const api=Object.freeze({versions,resolveTarget});if(typeof module!=='undefined')module.exports=api;else root.OBDocsConfig=api;
})(globalThis);
