"use client"

import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu"

import { cn } from "@/lib/utils"

export const DropdownMenu = DropdownMenuPrimitive.Root
export const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger

export function DropdownMenuContent({ className, ...props }: DropdownMenuPrimitive.DropdownMenuContentProps) {
  return <DropdownMenuPrimitive.Portal><DropdownMenuPrimitive.Content className={cn("ui-dropdown-content", className)} sideOffset={8} {...props} /></DropdownMenuPrimitive.Portal>
}

export function DropdownMenuCheckboxItem({ className, ...props }: DropdownMenuPrimitive.DropdownMenuCheckboxItemProps) {
  return <DropdownMenuPrimitive.CheckboxItem className={cn("ui-dropdown-item", className)} {...props} />
}
