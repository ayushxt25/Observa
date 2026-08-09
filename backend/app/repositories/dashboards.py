from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.dashboard import DashboardModel, DashboardWidgetModel
from app.schemas.dashboards import DashboardCreate, DashboardPatch, DashboardWidgetCreate, DashboardWidgetPatch


class DashboardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, workspace_id: str) -> list[DashboardModel]:
        stmt = (
            select(DashboardModel)
            .options(selectinload(DashboardModel.widgets))
            .where(DashboardModel.workspace_id == workspace_id)
            .order_by(DashboardModel.updated_at.desc(), DashboardModel.name)
        )
        return list(self.db.scalars(stmt).all())

    def get(self, dashboard_id: str, workspace_id: str) -> DashboardModel | None:
        stmt = (
            select(DashboardModel)
            .options(selectinload(DashboardModel.widgets))
            .where(DashboardModel.id == dashboard_id, DashboardModel.workspace_id == workspace_id)
        )
        return self.db.scalars(stmt).first()

    def create(self, payload: DashboardCreate, workspace_id: str) -> DashboardModel:
        dashboard = DashboardModel(name=payload.name, description=payload.description, workspace_id=workspace_id)
        for index, widget in enumerate(payload.widgets):
            dashboard.widgets.append(self._widget_from_create(widget))
        self.db.add(dashboard)
        self.db.commit()
        self.db.refresh(dashboard)
        return self.get(dashboard.id, workspace_id) or dashboard

    def update(self, dashboard: DashboardModel, payload: DashboardPatch) -> DashboardModel:
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(dashboard, key, value)
        self.db.commit()
        return self.get(dashboard.id, dashboard.workspace_id) or dashboard

    def delete(self, dashboard: DashboardModel) -> None:
        self.db.delete(dashboard)
        self.db.commit()

    def create_widget(self, dashboard: DashboardModel, payload: DashboardWidgetCreate) -> DashboardWidgetModel:
        widget = self._widget_from_create(payload)
        dashboard.widgets.append(widget)
        self.db.commit()
        self.db.refresh(widget)
        return widget

    def get_widget(self, dashboard_id: str, widget_id: str) -> DashboardWidgetModel | None:
        stmt = select(DashboardWidgetModel).where(
            DashboardWidgetModel.dashboard_id == dashboard_id,
            DashboardWidgetModel.id == widget_id,
        )
        return self.db.scalars(stmt).first()

    def update_widget(self, widget: DashboardWidgetModel, payload: DashboardWidgetPatch) -> DashboardWidgetModel:
        data = payload.model_dump(exclude_unset=True)
        warning = data.get("threshold_warning", widget.threshold_warning)
        critical = data.get("threshold_critical", widget.threshold_critical)
        if warning is not None and critical is not None and warning > critical:
            raise ValueError("thresholdWarning must be less than or equal to thresholdCritical")
        for key, value in data.items():
            setattr(widget, key, value)
        self.db.commit()
        self.db.refresh(widget)
        return widget

    def delete_widget(self, widget: DashboardWidgetModel) -> None:
        self.db.delete(widget)
        self.db.commit()

    def _widget_from_create(self, payload: DashboardWidgetCreate) -> DashboardWidgetModel:
        return DashboardWidgetModel(
            title=payload.title,
            type=payload.type,
            metric=payload.metric,
            service=payload.service,
            region=payload.region,
            aggregation=payload.aggregation,
            bucket=payload.bucket,
            time_range=payload.time_range,
            position=payload.position,
            width=payload.width,
            height=payload.height,
            threshold_warning=payload.threshold_warning,
            threshold_critical=payload.threshold_critical,
        )
