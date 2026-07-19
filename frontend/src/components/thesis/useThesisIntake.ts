/**
 * Live subscription to the mock store's thesis-intake state machine.
 * Subscribes on the store version (the intake object is mutated in place),
 * then reads the current state off getDB().
 */
import { useSyncExternalStore } from "react";
import { getDB, getVersion, subscribe, type ThesisIntakeState } from "@/mocks/state";

export function useThesisIntake(): ThesisIntakeState {
  useSyncExternalStore(subscribe, getVersion, getVersion);
  return getDB().thesisIntake;
}
