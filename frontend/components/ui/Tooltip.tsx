"use client";

import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/util/cn";

export const TooltipProvider = TooltipPrimitive.Provider;
export const Tooltip = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;

export const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <TooltipPrimitive.Content
    ref={ref}
    sideOffset={sideOffset}
    className={cn(
      "z-50 max-w-xs rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs text-fg shadow-e2",
      "data-[state=delayed-open]:animate-in data-[state=closed]:animate-out fade-in-0 fade-out-0",
      className
    )}
    {...props}
  />
));
TooltipContent.displayName = "TooltipContent";
