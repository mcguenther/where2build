/**
 * The wizard's stages, kept apart from the route table so the views that
 * navigate to one do not have to import the module that imports them.
 */

/** The three stages in order; the entries are the URL segments. The parcel and
 *  the fields it cannot supply are one stage: three inputs are not a step. */
export const WIZARD_STAGES = ["quelle", "werte", "flurstueck"];

/** Address of one stage, given its index or its slug. */
export const wizardStage = stage => ({
  name: "wizard",
  params: { stage: typeof stage === "number" ? WIZARD_STAGES[stage] : stage }
});
