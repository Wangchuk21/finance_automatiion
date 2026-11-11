"use client";

import * as ToastPrimitives from "@radix-ui/react-toast";

const Toaster = () => {
  return (
    <ToastPrimitives.Provider>
      <ToastPrimitives.Viewport className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-[380px] max-w-[90vw]" />
    </ToastPrimitives.Provider>
  );
};

export { Toaster };