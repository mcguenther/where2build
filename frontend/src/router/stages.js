/**
 * The wizard's stages, kept apart from the route table so the views that
 * navigate to one do not have to import the module that imports them.
 */

/** The stages in order; the entries are the URL segments.
 *
 *  „suche“ comes straight after the source because that is where the question
 *  actually is: a listing rarely names its Flurstück, and the step that finds
 *  it has to be able to show its working and be argued with. The direct route
 *  — Gemarkung and number typed in — skips it, because there is nothing to
 *  search for.
 *
 *  What the reader got out of the page used to be a step of its own. It is a
 *  list nobody needs to see to carry on, so it now sits folded away inside the
 *  search: dropping a link goes straight to searching, and the values are one
 *  click away for whoever wants to check or correct them. */
export const WIZARD_STAGES = ["quelle", "suche", "flurstueck"];

/** Address of one stage, given its index or its slug. */
export const wizardStage = stage => ({
  name: "wizard",
  params: { stage: typeof stage === "number" ? WIZARD_STAGES[stage] : stage }
});
