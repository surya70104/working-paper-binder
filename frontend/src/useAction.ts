// One request at a time, and the screen never shows a state the backend has left behind.
//
// run(action):
//   1. ignores the call if an action is already in flight (a second click sends nothing);
//   2. clears the previous error and marks the screen busy;
//   3. awaits the action; a refusal from the backend becomes the error message;
//   4. ALWAYS reloads the record afterwards, success or failure, and waits for the reload
//      before the screen stops being busy, so the buttons that come back are for the real
//      current state;
//   5. a reload failure is reported too, since the screen would otherwise be stale.
import { useCallback, useRef, useState } from "react";

export function useAction(reload: () => Promise<unknown>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const run = useCallback(
    async (action: () => Promise<unknown>): Promise<boolean> => {
      if (inFlight.current) return false;
      inFlight.current = true;
      setBusy(true);
      setError(null);
      let ok = true;
      try {
        await action();
      } catch (e) {
        ok = false;
        setError((e as Error).message);
      }
      try {
        await reload();
      } catch (e) {
        ok = false;
        setError((e as Error).message);
      } finally {
        inFlight.current = false;
        setBusy(false);
      }
      return ok;
    },
    [reload],
  );

  return { run, busy, error, setError };
}
