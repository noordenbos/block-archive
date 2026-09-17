'use strict';
// Regex runs off the UI thread. The caller terminates slow expressions.
let records = [];
self.onmessage = ({data}) => {
  if (data.records) { records = data.records; return; }
  try {
    const regex = data.mode === 'regex' && data.query ? new RegExp(data.query, 'i') : null;
    const text = data.query.toLocaleLowerCase();
    const keys = records.filter(item => (!data.kind || item.kind === data.kind) &&
      (!data.label || item.labels.includes(data.label)) &&
      (!data.metadataField || (Object.hasOwn(item.metadata,data.metadataField) && (!data.metadataValue || item.metadata[data.metadataField] === data.metadataValue))) &&
      (!data.selected || data.selected.includes(item.key)) &&
      (!text || (regex ? item.fields.some(field => regex.test(field)) : item.fields.join('\n').toLocaleLowerCase().includes(text))))
      .map(item => item.key);
    self.postMessage({generation: data.generation, keys});
  } catch (_) { self.postMessage({generation: data.generation, error: 'Invalid regular expression. Check the pattern.'}); }
};
