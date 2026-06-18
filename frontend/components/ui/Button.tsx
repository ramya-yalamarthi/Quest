"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/util/cn";

/**
 * Button — primary / secondary / ghost / destructive variants.
 *
 * Destructive uses `--danger` and is intended to be spatially separated
 * from the primary action (the brief calls out keeping Revert away from
 * Promote). Disabled state shows *why* via aria-disabled + tooltip wrapper
 * elsewhere; the styles are intentionally legible but discouraged.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium ring-offset-bg transition-colors duration-fast ease-out focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "bg-accent text-bg hover:bg-accent/90",
        secondary:
          "bg-surface-2 text-fg border border-border-strong hover:bg-surface-2/80",
        ghost:
          "text-fg hover:bg-surface-2",
        destructive:
          "bg-danger/15 text-danger border border-danger/40 hover:bg-danger/20",
        link:
          "text-accent underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-9 px-3.5 text-sm",
        lg: "h-10 px-4 text-sm",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size, className }))}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { buttonVariants };
