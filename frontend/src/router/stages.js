/**
 * The wizard's stages, kept apart from the route table so the views that
 * navigate to one do not have to import the module that imports them.
 */

/** The stages in order; the entries are the URL segments.
 *
 *  „suche“ sits between what was read and the parcel because that is where the
 *  question actually is: a listing rarely names its Flurstück, and the step
 *  that finds it has to be able to show its working and be argued with. The
 *  direct route — Gemarkung and number typed in — skips it, because there is
 *  nothing to search for. */
export const WIZARD_STAGES = ["quelle", "werte", "suche", "flurstueck"];

/** Address of one stage, given its index or its slug. */
export const wizardStage = stage => ({
  name: "wizard",
  params: { stage: typeof stage === "number" ? WIZARD_STAGES[stage] : stage }
});
