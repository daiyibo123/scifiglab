import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Float, Boolean,
    DateTime, ForeignKey,
)
from sqlalchemy.orm import relationship

from app.database.session import Base


# ---------------------------------------------------------------------------
# 1. User 用户表
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(128), unique=True, index=True, nullable=False)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    role = Column(String(32), default="user", index=True)
    is_email_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # relationships
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    experiments = relationship("Experiment", back_populates="user", cascade="all, delete-orphan")
    metrics = relationship("Metric", back_populates="user", cascade="all, delete-orphan")
    uploaded_files = relationship("UploadedFile", back_populates="user", cascade="all, delete-orphan")
    experiment_groups = relationship("ExperimentGroup", back_populates="user", cascade="all, delete-orphan")
    experiment_group_items = relationship("ExperimentGroupItem", back_populates="user", cascade="all, delete-orphan")
    ai_configs = relationship("UserAIConfig", back_populates="user", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# 2. EmailVerificationCode 邮箱验证码表
# ---------------------------------------------------------------------------
class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(128), nullable=False, index=True)
    code_hash = Column(String(256), nullable=False)
    purpose = Column(String(32), nullable=False, index=True)   # register / reset_password
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    send_count = Column(Integer, default=1)
    last_sent_at = Column(DateTime, default=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# 3. Project 项目表
# ---------------------------------------------------------------------------
class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    research_area = Column(String(128), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # relationships
    user = relationship("User", back_populates="projects")
    experiments = relationship("Experiment", back_populates="project", cascade="all, delete-orphan")
    metrics = relationship("Metric", back_populates="project", cascade="all, delete-orphan")
    uploaded_files = relationship("UploadedFile", back_populates="project", cascade="all, delete-orphan")
    experiment_groups = relationship("ExperimentGroup", back_populates="project", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# 4. Experiment 实验表
# ---------------------------------------------------------------------------
class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    experiment_code = Column(String(64), default="", index=True)
    description = Column(Text, default="")
    status = Column(String(32), default="pending", index=True)
    # status: pending / running / completed / failed / interrupted / abandoned / paper_used
    tags = Column(String(512), default="")
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    is_best = Column(Boolean, default=False)
    is_paper_used = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    note = Column(Text, default="")
    metadata_json = Column(Text, default="{}")

    # relationships
    user = relationship("User", back_populates="experiments")
    project = relationship("Project", back_populates="experiments")
    metrics = relationship("Metric", back_populates="experiment", cascade="all, delete-orphan")
    uploaded_files = relationship("UploadedFile", back_populates="experiment", cascade="all, delete-orphan")
    group_items = relationship("ExperimentGroupItem", back_populates="experiment", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# 5. Metric 指标表（通用 metric_name + metric_value）
# ---------------------------------------------------------------------------
class Metric(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False, index=True)
    step = Column(Integer, nullable=True)
    epoch = Column(Integer, nullable=True)
    metric_name = Column(String(128), nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    source_file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # relationships
    user = relationship("User", back_populates="metrics")
    project = relationship("Project", back_populates="metrics")
    experiment = relationship("Experiment", back_populates="metrics")
    source_file = relationship("UploadedFile", back_populates="sourced_metrics")


# ---------------------------------------------------------------------------
# 6. UploadedFile 文件表
# ---------------------------------------------------------------------------
class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False, index=True)
    file_name = Column(String(256), nullable=False)
    original_name = Column(String(256), nullable=False)
    file_type = Column(String(64), default="unknown")
    file_ext = Column(String(32), default="")
    file_size = Column(BigInteger, default=0)
    file_path = Column(String(512), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

    # relationships
    user = relationship("User", back_populates="uploaded_files")
    project = relationship("Project", back_populates="uploaded_files")
    experiment = relationship("Experiment", back_populates="uploaded_files")
    sourced_metrics = relationship("Metric", back_populates="source_file")


# ---------------------------------------------------------------------------
# 7. ExperimentGroup 实验组表
# ---------------------------------------------------------------------------
class ExperimentGroup(Base):
    __tablename__ = "experiment_groups"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    group_type = Column(String(32), default="custom", index=True)
    # group_type: ablation / comparison / parameter / final / custom
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # relationships
    user = relationship("User", back_populates="experiment_groups")
    project = relationship("Project", back_populates="experiment_groups")
    items = relationship("ExperimentGroupItem", back_populates="group", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# 8. ExperimentGroupItem 实验组成员表
# ---------------------------------------------------------------------------
class ExperimentGroupItem(Base):
    __tablename__ = "experiment_group_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("experiment_groups.id"), nullable=False, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False, index=True)
    display_name = Column(String(128), default="")
    sort_order = Column(Integer, default=0)
    curve_color = Column(String(32), default="")
    curve_style = Column(String(32), default="")
    marker_symbol = Column(String(32), default="")

    # relationships
    user = relationship("User", back_populates="experiment_group_items")
    group = relationship("ExperimentGroup", back_populates="items")
    experiment = relationship("Experiment", back_populates="group_items")


# ---------------------------------------------------------------------------
# 9. Announcement 公告表
# ---------------------------------------------------------------------------
class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    content = Column(Text, default="")
    display_type = Column(String(32), default="silent")   # silent / popup
    status = Column(String(32), default="draft", index=True)  # draft / published / ended
    start_at = Column(DateTime, nullable=True)   # NULL = 立即生效
    end_at = Column(DateTime, nullable=True)      # NULL = 永久
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# 10. SiteConfig 站点配置（功能开关、全局参数）
# ---------------------------------------------------------------------------
class SiteConfig(Base):
    __tablename__ = "site_config"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(Text, default="")
    description = Column(String(256), default="")
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# 11. Diagram 流程图表
# ---------------------------------------------------------------------------
class Diagram(Base):
    __tablename__ = "diagrams"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    title = Column(String(256), nullable=False, default="未命名流程图")
    description = Column(Text, default="")
    xml_data = Column(Text, default="")          # draw.io XML content
    thumbnail = Column(Text, default="")          # base64 PNG thumbnail
    layout_direction = Column(String(16), default="TB")  # TB / LR
    color_scheme = Column(String(64), default="default")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # relationships
    user = relationship("User", backref="diagrams")
    project = relationship("Project", backref="diagrams")


# ---------------------------------------------------------------------------
# 12. UserAIConfig 用户 AI 配置
# ---------------------------------------------------------------------------
class UserAIConfig(Base):
    __tablename__ = "user_ai_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String(64), nullable=False, index=True)
    auth_type = Column(String(32), default="api_key")  # api_key / oauth
    model = Column(String(128), default="")
    api_key_enc = Column(Text, default="")
    base_url = Column(String(256), default="")
    is_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="ai_configs")
