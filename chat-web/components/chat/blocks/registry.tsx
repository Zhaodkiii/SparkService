"use client";

import type { ReactNode } from "react";
import { BlockErrorBoundary, UnsupportedBlock } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";
import { DeepThoughtBlock, HtmlBlock, TextBlock, TranslatedTextBlock } from "@/components/chat/blocks/TextBlocks";
import { CaptureCardBlock, FileAttachmentsBlock, ImageGalleryBlock } from "@/components/chat/blocks/MediaBlocks";
import { ToolActivityBlock, ToolBlock } from "@/components/chat/blocks/ToolBlocks";
import { HealthCardsBlock, KnowledgeCardsBlock, NutritionCardsBlock, SearchSummaryBlock, StructuredHealthCardsBlock, WeatherConfigCardBlock } from "@/components/chat/blocks/CardsBlocks";
import { EnergyVisualizationBlock, EventsBlock, MapRouteBlock, NutritionReadVisualizationBlock, SleepVisualizationBlock, StepVisualizationBlock, WeatherVisualizationBlock, WorkoutVisualizationBlock } from "@/components/chat/blocks/VisualizationBlocks";
import { HealthResourceCandidateCardsBlock, LocationPermissionCardsBlock, PendingMemberToolCardsBlock, SmallTaskCardBlock, TaskCardsBlock, ToolConsentCardsBlock, ToolMemberSelectionCardsBlock, ToolQuestionCardsBlock } from "@/components/chat/blocks/TaskBlocks";
import { AssistantStatusCardBlock, ChatGuideCardBlock, ErrorBlock, HealthResourceReferenceBlock, MedicalDisclaimerCardBlock, MedicalRiskNoticeBlock } from "@/components/chat/blocks/NoticeBlocks";

type BlockRenderer = (props: BlockRenderProps) => ReactNode;

/**
 * Kind → renderer registry. Adding a new block kind only requires a renderer
 * entry here; the renderer receives the normalized `ChatBlockDTO` and is
 * isolated behind `BlockErrorBoundary` so one broken card never drops the
 * whole message.
 */
export const BLOCK_RENDERERS: Record<string, BlockRenderer> = {
  text: TextBlock,
  deepThought: DeepThoughtBlock,
  tool: ToolBlock,
  imageGallery: ImageGalleryBlock,
  fileAttachments: FileAttachmentsBlock,
  knowledgeCards: KnowledgeCardsBlock,
  translatedText: TranslatedTextBlock,
  mapRoute: MapRouteBlock,
  events: EventsBlock,
  healthCards: HealthCardsBlock,
  pendingMemberToolCards: PendingMemberToolCardsBlock,
  toolQuestionCards: ToolQuestionCardsBlock,
  toolMemberSelectionCards: ToolMemberSelectionCardsBlock,
  healthResourceCandidateCards: HealthResourceCandidateCardsBlock,
  toolConsentCards: ToolConsentCardsBlock,
  locationPermissionCards: LocationPermissionCardsBlock,
  structuredHealthCards: StructuredHealthCardsBlock,
  sleepVisualization: SleepVisualizationBlock,
  stepVisualization: StepVisualizationBlock,
  energyVisualization: EnergyVisualizationBlock,
  nutritionReadVisualization: NutritionReadVisualizationBlock,
  weatherVisualization: WeatherVisualizationBlock,
  weatherConfigCard: WeatherConfigCardBlock,
  searchSummary: SearchSummaryBlock,
  nutritionCards: NutritionCardsBlock,
  workoutVisualization: WorkoutVisualizationBlock,
  captureCard: CaptureCardBlock,
  html: HtmlBlock,
  smallTaskCard: SmallTaskCardBlock,
  taskCards: TaskCardsBlock,
  error: ErrorBlock,
  assistantStatusCard: AssistantStatusCardBlock,
  healthResourceReference: HealthResourceReferenceBlock,
  medicalRiskNotice: MedicalRiskNoticeBlock,
  medicalDisclaimerCard: MedicalDisclaimerCardBlock,
  chatGuideCard: ChatGuideCardBlock,
  toolCall: ToolActivityBlock,
  toolResult: ToolActivityBlock,
};

export function renderBlock(props: BlockRenderProps): ReactNode {
  const Renderer = BLOCK_RENDERERS[props.block.kind];
  if (!Renderer) return <UnsupportedBlock block={props.block} />;
  return <BlockErrorBoundary block={props.block}><Renderer {...props} /></BlockErrorBoundary>;
}