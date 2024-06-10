import logging
import typing
from copy import deepcopy

from core.models import (
    SoftDeleteExportableManager,
    SoftDeleteExportableModel,
    abstract_base_auditable_model_factory,
)
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db import models
from django_lifecycle import AFTER_CREATE, LifecycleModelMixin, hook
from flag_engine.segments import constants

from audit.constants import (
    SEGMENT_CREATED_MESSAGE,
    SEGMENT_DELETED_MESSAGE,
    SEGMENT_UPDATED_MESSAGE,
)
from audit.related_object_type import RelatedObjectType
from features.models import Feature
from metadata.models import Metadata
from projects.models import Project

from .managers import SegmentManager

logger = logging.getLogger(__name__)


class Segment(
    LifecycleModelMixin,
    SoftDeleteExportableModel,
    abstract_base_auditable_model_factory(["uuid"]),
):
    history_record_class_path = "segments.models.HistoricalSegment"
    related_object_type = RelatedObjectType.SEGMENT

    name = models.CharField(max_length=2000)
    description = models.TextField(null=True, blank=True)
    project = models.ForeignKey(
        Project,
        # Cascade deletes are decouple from the Django ORM. See this PR for details.
        # https://github.com/Flagsmith/flagsmith/pull/3360/
        on_delete=models.DO_NOTHING,
        related_name="segments",
    )
    feature = models.ForeignKey(
        Feature, on_delete=models.CASCADE, related_name="segments", null=True
    )

    version = models.IntegerField(default=1)
    version_of = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="versioned_segments",
        null=True,
        blank=True,
    )
    metadata = GenericRelation(Metadata)

    # Only serves segments that are the canonical version.
    objects = SegmentManager()

    # Includes versioned segments.
    all_objects = SoftDeleteExportableManager()

    class Meta:
        ordering = ("id",)  # explicit ordering to prevent pagination warnings

    def __str__(self):
        return "Segment - %s" % self.name

    @staticmethod
    def id_exists_in_rules_data(rules_data: typing.List[dict]) -> bool:
        """
        Given a list of segment rules, return whether any of the rules or conditions contain an id.

        :param rules_data: list of segment rules (in the form {"id": 1, "rules": [], "conditions": [], "typing": ""})
        :return: boolean value detailing whether any id attributes were found
        """

        _rules_data = deepcopy(rules_data)
        for rule_data in _rules_data:
            if rule_data.get("id"):
                return True

            conditions_to_check = rule_data.get("conditions", [])
            rules_to_check = rule_data.get("rules", [])

            while rules_to_check:
                rule = rules_to_check.pop()
                if rule.get("id"):
                    return True
                rules_to_check.extend(rule.get("rules", []))
                conditions_to_check.extend(rule.get("conditions", []))

            while conditions_to_check:
                condition = conditions_to_check.pop()
                if condition.get("id"):
                    return True

        return False

    @hook(AFTER_CREATE, when="version_of", is_now=None)
    def set_version_of_to_self_if_none(self):
        """
        This allows the segment model to reference all versions of
        itself including itself.
        """
        self.version_of = self
        self.save()

    def deep_clone(self) -> "Segment":
        new_segment = Segment.objects.create(
            name=self.name,
            description=self.description,
            project=self.project,
            feature=self.feature,
            version=self.version,
            version_of=self,
        )

        self.version += 1
        self.save()

        new_rules = []
        for rule in self.rules.all():
            new_rule = rule.deep_clone(new_segment)
            new_rules.append(new_rule)

        new_segment.refresh_from_db()

        assert (
            len(self.rules.all()) == len(new_rules) == len(new_segment.rules.all())
        ), "Mismatch during rules creation"

        return new_segment

    def get_create_log_message(self, history_instance) -> typing.Optional[str]:
        return SEGMENT_CREATED_MESSAGE % self.name

    def get_update_log_message(self, history_instance) -> typing.Optional[str]:
        return SEGMENT_UPDATED_MESSAGE % self.name

    def get_delete_log_message(self, history_instance) -> typing.Optional[str]:
        return SEGMENT_DELETED_MESSAGE % self.name

    def _get_project(self):
        return self.project


class SegmentRule(SoftDeleteExportableModel):
    ALL_RULE = "ALL"
    ANY_RULE = "ANY"
    NONE_RULE = "NONE"

    RULE_TYPES = ((ALL_RULE, "all"), (ANY_RULE, "any"), (NONE_RULE, "none"))

    segment = models.ForeignKey(
        Segment, on_delete=models.CASCADE, related_name="rules", null=True, blank=True
    )
    rule = models.ForeignKey(
        "self", on_delete=models.CASCADE, related_name="rules", null=True, blank=True
    )

    type = models.CharField(max_length=50, choices=RULE_TYPES)

    def clean(self):
        super().clean()
        parents = [self.segment, self.rule]
        num_parents = sum(parent is not None for parent in parents)
        if num_parents != 1:
            raise ValidationError(
                "Segment rule must have exactly one parent, %d found", num_parents
            )

    def __str__(self):
        return "%s rule for %s" % (
            self.type,
            str(self.segment) if self.segment else str(self.rule),
        )

    def get_segment(self):
        """
        rules can be a child of a parent rule instead of a segment, this method iterates back up the tree to find the
        segment

        TODO: denormalise the segment information so that we don't have to make multiple queries here in complex cases
        """
        rule = self
        while not rule.segment:
            rule = rule.rule
        return rule.segment

    def deep_clone(self, versioned_segment: Segment) -> "SegmentRule":
        if self.rule:
            assert False, "Unexpected rule, expecting segment set not rule"
        new_rule = SegmentRule.objects.create(
            segment=versioned_segment,
            type=self.type,
        )

        new_conditions = []
        for condition in self.conditions.all():
            new_condition = Condition(
                operator=condition.operator,
                property=condition.property,
                value=condition.value,
                description=condition.description,
                created_with_segment=condition.created_with_segment,
                rule=new_rule,
            )
            new_conditions.append(new_condition)
        Condition.objects.bulk_create(new_conditions)

        for sub_rule in self.rules.all():
            if sub_rule.rules.exists():
                logger.error("Expected two layers of rules, not more")

            new_sub_rule = SegmentRule.objects.create(
                rule=new_rule,
                type=sub_rule.type,
            )

            new_conditions = []
            for condition in sub_rule.conditions.all():
                new_condition = Condition(
                    operator=condition.operator,
                    property=condition.property,
                    value=condition.value,
                    description=condition.description,
                    created_with_segment=condition.created_with_segment,
                    rule=new_sub_rule,
                )
                new_conditions.append(new_condition)
            Condition.objects.bulk_create(new_conditions)

        return new_rule


class Condition(
    SoftDeleteExportableModel, abstract_base_auditable_model_factory(["uuid"])
):
    history_record_class_path = "segments.models.HistoricalCondition"
    related_object_type = RelatedObjectType.SEGMENT

    CONDITION_TYPES = (
        (constants.EQUAL, "Exactly Matches"),
        (constants.GREATER_THAN, "Greater than"),
        (constants.LESS_THAN, "Less than"),
        (constants.CONTAINS, "Contains"),
        (constants.GREATER_THAN_INCLUSIVE, "Greater than or equal to"),
        (constants.LESS_THAN_INCLUSIVE, "Less than or equal to"),
        (constants.NOT_CONTAINS, "Does not contain"),
        (constants.NOT_EQUAL, "Does not match"),
        (constants.REGEX, "Matches regex"),
        (constants.PERCENTAGE_SPLIT, "Percentage split"),
        (constants.MODULO, "Modulo Operation"),
        (constants.IS_SET, "Is set"),
        (constants.IS_NOT_SET, "Is not set"),
        (constants.IN, "In"),
    )

    operator = models.CharField(choices=CONDITION_TYPES, max_length=500)
    property = models.CharField(blank=True, null=True, max_length=1000)
    value = models.CharField(
        max_length=settings.SEGMENT_CONDITION_VALUE_LIMIT, blank=True, null=True
    )
    description = models.TextField(blank=True, null=True)

    created_with_segment = models.BooleanField(
        default=False,
        help_text="Field to denote whether a condition was created along with segment or added after creation.",
    )

    rule = models.ForeignKey(
        SegmentRule, on_delete=models.CASCADE, related_name="conditions"
    )

    def __str__(self):
        return "Condition for %s: %s %s %s" % (
            str(self.rule),
            self.property,
            self.operator,
            self.value,
        )

    def get_update_log_message(self, history_instance) -> typing.Optional[str]:
        return f"Condition updated on segment '{self._get_segment().name}'."

    def get_create_log_message(self, history_instance) -> typing.Optional[str]:
        if not self.created_with_segment:
            return f"Condition added to segment '{self._get_segment().name}'."

    def get_delete_log_message(self, history_instance) -> typing.Optional[str]:
        if not self._get_segment().deleted_at:
            return f"Condition removed from segment '{self._get_segment().name}'."

    def get_audit_log_related_object_id(self, history_instance) -> int:
        return self._get_segment().id

    def _get_segment(self) -> Segment:
        """
        Temporarily cache the segment on the condition object to reduce number of queries.
        """
        if not hasattr(self, "segment"):
            setattr(self, "segment", self.rule.get_segment())
        return self.segment

    def _get_project(self) -> typing.Optional[Project]:
        return self.rule.get_segment().project


class WhitelistedSegment(models.Model):
    """
    In order to grandfather in existing segments, these models represent segments
    that do not conform to the SEGMENT_RULES_CONDITIONS_LIMIT and may have
    more than the typically allowed number of segment rules and conditions.
    """

    segment = models.OneToOneField(
        Segment,
        on_delete=models.CASCADE,
        related_name="whitelisted_segment",
    )
    created_at = models.DateTimeField(null=True, auto_now_add=True)
    updated_at = models.DateTimeField(null=True, auto_now=True)
