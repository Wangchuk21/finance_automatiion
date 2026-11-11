import * as React from "react";
import { cn } from "@/lib/utils";

export function Separator({
  className,
  orientation = "horizontal",
  decorative = true,
  ...props
}: React.ComponentPropsWithoutRef<"hr"> & {
  orientation?: "horizontal" | "vertical";
  decorative?: boolean;
}) {
  return (
    <hr
      className={cn(
        "shrink-0 bg-border",
        orientation === "horizontal" ? "w-full h-[1px]" : "h-full w-[1px]",
        className
      )}
      aria-orientation={orientation}
      aria-hidden={decorative}
      {...props}
    />
  );
}