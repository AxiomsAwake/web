'use strict';
// Format providers admit/open native bytes; this workflow never reconstructs source.
window.AxiomsNativeMomentJourney = async function (action, snapshot, {store, admit, open}) {
  if (action?.kind === 'keep') {
    const saved = await store.keep(action.name, snapshot);
    return {reload: false, message: `${saved.duplicate ? 'Already kept' : 'Kept'}: ${saved.card.name}`};
  }
  if (action?.kind !== 'reopen') throw new Error('No experiment capture is pending.');
  const target = await store.read(action.id);
  if (target.format !== snapshot.format) throw new Error('This moment needs its matching native editor.');
  await admit(target.bytes);
  // Complete the safety copy before opening. A failed copy leaves the live draft
  // untouched; a failed open still leaves a durable copy of the current draft.
  const recovery = await store.keep(('Before ' + target.name).slice(0, 64), snapshot);
  await open(target);
  return {reload: true, recovery: recovery.card.id, message: 'Current edits kept; reopening ' + target.name};
};
