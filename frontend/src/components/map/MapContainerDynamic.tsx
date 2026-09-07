"use client";

import dynamic from "next/dynamic";
import { LoadingView } from "../ui/StateViews";

export const MapContainerDynamic = dynamic(
  () => import("./OceanMap"),
  {
    ssr: false,
    loading: () => (
      <div className="w-full h-full flex items-center justify-center bg-ocean-abyss min-h-[450px]">
        <LoadingView label="Initializing bathymetric geospatial canvas..." />
      </div>
    ),
  }
);
