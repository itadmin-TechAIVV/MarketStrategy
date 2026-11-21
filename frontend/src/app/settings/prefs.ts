import { api, type Preferences } from "../../api";

/** Save a preference on the server, then apply the stored set. The UI has already changed locally,
 *  so a failed save is not shown: the server copy catches up on the next change. */
export async function savePreference(change: Partial<Preferences>, apply: (p: Preferences) => void) {
  try {
    apply(await api.updatePreferences(change));
  } catch {
    /* keep the local change */
  }
}
