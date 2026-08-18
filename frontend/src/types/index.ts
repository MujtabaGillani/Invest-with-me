/**
 * Domain type aliases over the generated OpenAPI types.
 *
 * `api.d.ts` is generated from the backend's schema and must never be edited by
 * hand (`npm run codegen` regenerates it). Everything in the app imports from
 * *this* file instead, for two reasons:
 *
 * 1. `components['schemas']['FundamentalsReport']` is unreadable at every call
 *    site, and a rename in the generator's output would touch a hundred files.
 * 2. It makes the surface the frontend actually depends on explicit. If a type
 *    is not aliased here, the app is not using it.
 *
 * There are no hand-written shapes below - only aliases. Any field the UI needs
 * has to exist on the server first, so the two cannot drift.
 */

import type { components } from './api';

type Schemas = components['schemas'];

// --- Metadata and provenance -----------------------------------------------

export type Metadata = Schemas['MetadataRead'];
export type ProviderInfo = Schemas['ProviderInfo'];
export type EnumOption = Schemas['EnumOption'];
export type Health = Schemas['HealthRead'];
export type Disclaimer = Schemas['Disclaimer'];

// --- Vocabulary -------------------------------------------------------------

export type Sector = Schemas['Sector'];
export type MetricVerdict = Schemas['MetricVerdict'];
export type TimeHorizon = Schemas['TimeHorizon'];
export type RiskTolerance = Schemas['RiskTolerance'];
export type TradePlanStatus = Schemas['TradePlanStatus'];
export type TradeSide = Schemas['TradeSide'];
export type AlertKind = Schemas['AlertKind'];
export type AlertSeverity = Schemas['AlertSeverity'];
export type TrendDirection = Schemas['TrendDirection'];
export type RsiZone = Schemas['RsiZone'];
export type MovingAveragePosition = Schemas['MovingAveragePosition'];
export type VolumeConfirmation = Schemas['VolumeConfirmation'];

// --- Companies and market data ---------------------------------------------

export type CompanySummary = Schemas['CompanySummary'];
export type CompanyDetail = Schemas['CompanyDetail'];
export type AnnualFinancials = Schemas['AnnualFinancialsRead'];
export type PriceBar = Schemas['PriceBarRead'];
export type PriceHistory = Schemas['PriceHistoryRead'];
export type CompanyPage = Schemas['Page_CompanySummary_'];

// --- Analysis ---------------------------------------------------------------

export type FundamentalsReport = Schemas['FundamentalsReport'];
export type FundamentalsScore = Schemas['FundamentalsScore'];
export type MetricAssessment = Schemas['MetricAssessment'];
export type YearValue = Schemas['YearValue'];
export type RedFlag = Schemas['RedFlag'];
export type StatementReview = Schemas['StatementReview'];
export type StatementCheck = Schemas['StatementCheck'];
export type TechnicalReport = Schemas['TechnicalReport'];
export type IndicatorReading = Schemas['IndicatorReading'];

// --- Investor profile -------------------------------------------------------

export type InvestorProfile = Schemas['InvestorProfileRead'];
export type InvestorProfileInput = Schemas['InvestorProfileUpsert'];

// --- Watchlist --------------------------------------------------------------

export type WatchlistItem = Schemas['WatchlistItemRead'];
export type WatchlistItemInput = Schemas['WatchlistItemCreate'];
export type WatchlistItemPatch = Schemas['WatchlistItemUpdate'];

// --- Trade plans ------------------------------------------------------------

export type TradePlan = Schemas['TradePlanRead'];
export type TradePlanDetail = Schemas['TradePlanDetail'];
export type TradePlanInput = Schemas['TradePlanCreate'];
export type TradePlanPatch = Schemas['TradePlanUpdate'];
export type TradePlanReadiness = Schemas['TradePlanReadiness'];
export type ChecklistItem = Schemas['ChecklistItemRead'];
export type PositionSizingCheck = Schemas['PositionSizingCheck'];
export type PlanReview = Schemas['PlanReviewRead'];
export type PlanReviewInput = Schemas['TradePlanReviewCreate'];
export type TradePlanPage = Schemas['Page_TradePlanRead_'];

/**
 * The five pre-buy checklist field names, as the API keys them.
 *
 * Derived from the patch type rather than re-listed, so adding a sixth question
 * server-side is a compile error here instead of a silently missing checkbox.
 */
export type ChecklistKey = keyof Pick<
  TradePlanPatch,
  | 'understands_business'
  | 'revenue_and_profit_healthy'
  | 'debt_manageable_vs_peers'
  | 'comfortable_with_drawdown'
  | 'position_size_appropriate'
>;

// --- Portfolio --------------------------------------------------------------

export type Portfolio = Schemas['PortfolioRead'];
export type PortfolioSummary = Schemas['PortfolioSummary'];
export type Holding = Schemas['HoldingRead'];
export type SectorAllocation = Schemas['SectorAllocation'];
export type ConcentrationWarning = Schemas['ConcentrationWarning'];
export type Trade = Schemas['TradeRead'];
export type TradeInput = Schemas['TradeCreate'];

// --- Alerts -----------------------------------------------------------------

export type Alert = Schemas['AlertRead'];
export type AlertEvaluation = Schemas['AlertEvaluationResult'];

// --- Generic responses ------------------------------------------------------

export type MessageResponse = Schemas['MessageResponse'];
