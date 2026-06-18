"use client";

import * as React from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { cva, type VariantProps } from "class-variance-authority";
import { X } from "lucide-react";
import { cn } from "@/lib/util/cn";

export const ToastProvider = ToastPrimitive.Provider;

const toastVariants = cva(
  "group pointer-events-auto relative flex w-full items-start gap-3 overflow-hidden rounded-md border p-3 pr-8 shadow-e2 data-[swipe=move]:transition-none data-[state=open]:animate-in data-[state=closed]:animate-out slide-in-from-bottom-2 fade-in-0",
  {
    variants: {
      tone: {
        default: "bg-surface border-border text-fg",
        info: "bg-info/10 border-info/40 text-info",
        ok: "bg-ok/10 border-ok/40 text-ok",
        warn: "bg-warn/10 border-warn/40 text-warn",
        danger: "bg-danger/15 border-danger/40 text-danger",
      },
    },
    defaultVariants: { tone: "default" },
  }
);

export const Toast = React.forwardRef<
  React.ElementRef<typeof ToastPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Root> &
    VariantProps<typeof toastVariants>
>(({ className, tone, ...props }, ref) => (
  <ToastPrimitive.Root
    ref={ref}
    className={cn(toastVariants({ tone }), className)}
    {...props}
  />
));
Toast.displayName = "Toast";

export const ToastTitle = React.forwardRef<
  React.ElementRef<typeof ToastPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Title>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Title
    ref={ref}
    className={cn("text-sm font-medium text-fg", className)}
    {...props}
  />
));
ToastTitle.displayName = "ToastTitle";

export const ToastDescription = React.forwardRef<
  React.ElementRef<typeof ToastPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Description>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Description
    ref={ref}
    className={cn("text-xs text-fg-muted", className)}
    {...props}
  />
));
ToastDescription.displayName = "ToastDescription";

export const ToastClose = React.forwardRef<
  React.ElementRef<typeof ToastPrimitive.Close>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Close>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Close
    ref={ref}
    className={cn(
      "absolute right-1 top-1 rounded p-1 text-fg-muted hover:text-fg hover:bg-surface-2 transition-colors",
      className
    )}
    aria-label="Dismiss notification"
    {...props}
  >
    <X className="size-3.5" aria-hidden />
  </ToastPrimitive.Close>
));
ToastClose.displayName = "ToastClose";

export const ToastViewport = React.forwardRef<
  React.ElementRef<typeof ToastPrimitive.Viewport>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Viewport>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Viewport
    ref={ref}
    className={cn(
      "fixed bottom-4 right-4 z-[100] flex max-h-screen w-80 flex-col gap-2 outline-none",
      className
    )}
    {...props}
  />
));
ToastViewport.displayName = "ToastViewport";
