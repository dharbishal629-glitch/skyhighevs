import { Router, type IRouter } from "express";
import healthRouter from "./health";
import workersRouter from "./workers";
import workerListRouter from "./workerList";
import tokensRouter from "./tokens";
import dashboardRouter from "./dashboard";
import zeusRouter from "./zeus";
import toolConfigRouter from "./toolConfig";
import payoutRouter from "./payout";
import toolFileRouter from "./toolFile";
import launcherRouter from "./launcher";
import workerPortalRouter from "./workerPortal";
import envSettingsRouter from "./envSettings";
import adminAuthRouter from "./adminAuth";
import workerEnvRouter from "./workerEnv";

const router: IRouter = Router();

router.use(healthRouter);
router.use(adminAuthRouter);
router.use(workersRouter);
router.use(workerListRouter);
router.use(tokensRouter);
router.use(dashboardRouter);
router.use(zeusRouter);
router.use(toolConfigRouter);
router.use(payoutRouter);
router.use(toolFileRouter);
router.use(launcherRouter);
router.use(workerPortalRouter);
router.use(envSettingsRouter);
router.use(workerEnvRouter);

export default router;
