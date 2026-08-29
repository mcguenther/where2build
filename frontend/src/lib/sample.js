/**
 * Starting state.
 *
 * Deliberately empty. Everything shown in this application comes from a real
 * service — the cadastre, the land-value register, the routing engine, or a
 * page the model actually read. There is no example plot and no example house
 * type, because once a made-up figure sits in the same table as an official one
 * nothing on screen tells them apart.
 */

/** Shape of the stored document. Version 1 used German keys; `validate()`
 *  migrates such a file rather than dropping the user's plots. */
export const SCHEMA_VERSION = 2;

export const emptyState = () => ({
  version: SCHEMA_VERSION,
  plots: [],
  houseTypes: [],
  destinations: [],
  selection: []
});
