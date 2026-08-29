/**
 * Starting state.
 *
 * Deliberately empty. Everything shown in this application comes from a real
 * service — the cadastre, the land-value register, the routing engine, or a
 * page the model actually read. There is no example plot and no example house
 * type, because once a made-up figure sits in the same table as an official one
 * nothing on screen tells them apart.
 */
export const emptyState = () => ({
  version: 1,
  grundstuecke: [],
  haustypen: [],
  ziele: [],
  auswahl: []
});
