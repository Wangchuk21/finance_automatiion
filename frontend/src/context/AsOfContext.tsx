import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useAuth } from "@/context/AuthContext";
import {
  AS_OF_STORAGE_KEY,
  dashboardApi,
  setGlobalAsOf,
} from "@/lib/api";

const MONTH_NAMES = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/** Normalise any date-like value to the first-of-month key used by the API. */
function toMonthKey(value: string | null | undefined): string | null {
  if (!value) return null;
  const match = String(value).trim().match(/^(\d{4})-(\d{2})/);
  if (!match) return null;
  const month = Number(match[2]);
  if (month < 1 || month > 12) return null;
  return `${match[1]}-${String(month).padStart(2, "0")}`;
}

/** Human-readable label used in the header and page subtitles. */
export function formatAsOfLabel(value: string | null | undefined): string {
  const key = toMonthKey(value);
  if (!key) return "Latest";
  const [year, month] = key.split("-");
  return `${MONTH_NAMES[Number(month) - 1]} ${year}`;
}

interface AsOfContextType {
  /** Selected month key (YYYY-MM), or null for no cutoff (latest). */
  asOf: string | null;
  /** Human-readable label for the current selection. */
  label: string;
  /** Available month keys, newest first. */
  options: string[];
  /** Only finance users may change the cutoff. */
  canSelect: boolean;
  /** True while the available dates are loading. */
  loading: boolean;
  setAsOf: (value: string | null) => void;
}

const AsOfContext = createContext<AsOfContextType | null>(null);

export function AsOfProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const canSelect =
    user?.role === "admin" || user?.role === "finance_uploader";

  const [options, setOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [asOf, setAsOfState] = useState<string | null>(() => {
    try {
      return toMonthKey(localStorage.getItem(AS_OF_STORAGE_KEY));
    } catch {
      return null;
    }
  });

  // Keep the API layer in sync so every GET request carries the cutoff.
  useEffect(() => {
    setGlobalAsOf(asOf);
  }, [asOf]);

  // Load the distinct confirmed upload months. Reload after login/logout so a
  // fresh session sees its own data.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    dashboardApi
      .getAsOfDates()
      .then((res) => {
        if (!cancelled) setOptions(res.dates || []);
      })
      .catch(() => {
        if (!cancelled) setOptions([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  const setAsOf = useCallback((value: string | null) => {
    const key = toMonthKey(value);
    // Update the API layer synchronously: child page effects may run before
    // this provider's own effect when the selected month changes.
    setGlobalAsOf(key);
    setAsOfState(key);
    try {
      if (key) localStorage.setItem(AS_OF_STORAGE_KEY, key);
      else localStorage.removeItem(AS_OF_STORAGE_KEY);
    } catch {
      // localStorage may be unavailable; the in-memory value still applies.
    }
  }, []);

  const monthOptions = useMemo(() => {
    const unique = new Set<string>();
    for (const date of options) {
      const key = toMonthKey(date);
      if (key) unique.add(key);
    }
    return Array.from(unique).sort().reverse();
  }, [options]);

  const label = useMemo(() => {
    if (asOf) return formatAsOfLabel(asOf);
    return monthOptions.length ? formatAsOfLabel(monthOptions[0]) : "Latest";
  }, [asOf, monthOptions]);

  return (
    <AsOfContext.Provider
      value={{
        asOf,
        label,
        options: monthOptions,
        canSelect,
        loading,
        setAsOf,
      }}
    >
      {children}
    </AsOfContext.Provider>
  );
}

export function useAsOf(): AsOfContextType {
  const context = useContext(AsOfContext);
  if (!context) {
    throw new Error("useAsOf must be used within an AsOfProvider");
  }
  return context;
}
