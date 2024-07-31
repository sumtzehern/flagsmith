import typing

from drf_yasg.utils import swagger_serializer_method
from flag_engine.features.models import FeatureStateModel
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from environments.identities.models import Identity
from environments.models import Environment
from environments.serializers import EnvironmentSerializerFull
from features.models import FeatureState
from features.serializers import (
    FeatureStateSerializerFull,
    SDKFeatureStateSerializer,
)


class IdentifierOnlyIdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Identity
        fields = ("identifier",)


class IdentitySerializerFull(serializers.ModelSerializer):
    identity_features = FeatureStateSerializerFull(many=True)
    environment = EnvironmentSerializerFull()

    class Meta:
        model = Identity
        fields = ("id", "identifier", "identity_features", "environment")


class IdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Identity
        fields = ("id", "identifier", "environment")
        read_only_fields = ("id", "environment")

    def save(self, **kwargs):
        environment = kwargs.get("environment")
        identifier = self.validated_data.get("identifier")

        if Identity.objects.filter(
            environment=environment, identifier=identifier
        ).exists():
            raise ValidationError(
                {
                    "identifier": "Identity with identifier '%s' already exists in this environment"
                    % identifier
                }
            )
        return super(IdentitySerializer, self).save(**kwargs)


class SDKIdentitiesResponseSerializer(serializers.Serializer):
    class _TraitSerializer(serializers.Serializer):
        trait_key = serializers.CharField()
        trait_value = serializers.Field(
            help_text="Can be of type string, boolean, float or integer."
        )

    flags = serializers.ListField(child=SDKFeatureStateSerializer())
    traits = serializers.ListSerializer(child=_TraitSerializer())


class SDKIdentitiesQuerySerializer(serializers.Serializer):
    identifier = serializers.CharField(required=True)
    transient = serializers.BooleanField(default=False)


class IdentityAllFeatureStatesFeatureSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    type = serializers.CharField()


class IdentityAllFeatureStatesSegmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class IdentityAllFeatureStatesMVFeatureOptionSerializer(serializers.Serializer):
    value = serializers.SerializerMethodField(
        help_text="Can be any of the following types: integer, boolean, string."
    )

    def get_value(self, instance) -> typing.Union[str, int, bool]:
        return instance.value


class IdentityAllFeatureStatesMVFeatureStateValueSerializer(serializers.Serializer):
    multivariate_feature_option = IdentityAllFeatureStatesMVFeatureOptionSerializer()
    percentage_allocation = serializers.FloatField()


class IdentityAllFeatureStatesSerializer(serializers.Serializer):
    feature = IdentityAllFeatureStatesFeatureSerializer()
    enabled = serializers.BooleanField()
    feature_state_value = serializers.SerializerMethodField(
        help_text="Can be any of the following types: integer, boolean, string."
    )
    overridden_by = serializers.SerializerMethodField(
        help_text="One of: null, 'SEGMENT', 'IDENTITY'."
    )
    segment = serializers.SerializerMethodField()
    multivariate_feature_state_values = (
        IdentityAllFeatureStatesMVFeatureStateValueSerializer(many=True)
    )

    def get_feature_state_value(
        self, instance: typing.Union[FeatureState, FeatureStateModel]
    ) -> typing.Union[str, int, bool]:
        identity = self.context["identity"]
        environment_api_key = self.context["environment_api_key"]

        environment = Environment.get_from_cache(environment_api_key)
        hash_key = identity.get_hash_key(
            environment.use_identity_composite_key_for_hashing
        )

        if isinstance(instance, FeatureState):
            return instance.get_feature_state_value_by_hash_key(hash_key)

        return instance.get_value(hash_key)

    def get_overridden_by(self, instance) -> typing.Optional[str]:
        if getattr(instance, "feature_segment_id", None) is not None:
            return "SEGMENT"
        elif getattr(
            instance, "identity_id", None
        ) or instance.feature.name in self.context.get("identity_feature_names", []):
            return "IDENTITY"
        return None

    @swagger_serializer_method(
        serializer_or_field=IdentityAllFeatureStatesSegmentSerializer
    )
    def get_segment(self, instance) -> typing.Optional[typing.Dict[str, typing.Any]]:
        if getattr(instance, "feature_segment_id", None) is not None:
            return IdentityAllFeatureStatesSegmentSerializer(
                instance=instance.feature_segment.segment
            ).data
        return None


class IdentitySourceIdentityRequestSerializer(serializers.Serializer):
    source_identity_id = serializers.IntegerField(
        required=True,
        help_text="ID of the source identity to clone feature states from.",
    )
