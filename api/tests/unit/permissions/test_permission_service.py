from permissions.permission_service import is_user_project_admin
from projects.models import Project


def test_is_user_project_admin_returns_true_for_org_admin(
    organisation, admin_user, project
):
    assert is_user_project_admin(admin_user, project) is True


def test_is_user_project_admin_returns_true_for_user_with_admin_permission_through_user_itself(
    organisation, test_user, project, user_project_permission
):
    # Given
    user_project_permission.admin = True
    user_project_permission.save()

    # Then
    assert is_user_project_admin(test_user, project) is True


def test_is_user_project_admin_returns_true_for_user_with_admin_permission_through_user_group(
    organisation,
    test_user,
    project,
    user_project_permission_group,
    user_permission_group,
):
    # Given
    user_permission_group.users.add(test_user)

    user_project_permission_group.admin = True
    user_project_permission_group.save()

    # Then
    assert is_user_project_admin(test_user, project) is True


def test_is_user_project_admin_returns_true_for_user_with_admin_permission_through_role_attached_to_user(
    organisation,
    test_user,
    project,
    user_role,
    role_project_permission,
):
    # Given
    role_project_permission.admin = True
    role_project_permission.save()

    # Then
    assert is_user_project_admin(test_user, project) is True


def test_is_user_project_admin_returns_true_for_user_with_admin_permission_through_role_attached_to_group(
    organisation,
    test_user,
    project,
    group_role,
    role_project_permission,
    user_permission_group,
):
    # Given
    # Add the user to the group
    user_permission_group.users.add(test_user)

    role_project_permission.admin = True
    role_project_permission.save()

    # Then
    assert is_user_project_admin(test_user, project) is True


def test_is_user_project_admin_returns_false_for_user_with_no_permission(
    organisation,
    test_user,
    project,
):
    assert is_user_project_admin(test_user, project) is False


def test_is_user_project_admin_returns_false_for_user_with_admin_permission_of_other_org(
    admin_user,
    project,
    other_project,
):
    assert is_user_project_admin(admin_user, other_project) is False


def test_is_user_project_admin_returns_false_for_user_with_admin_permission_of_other_project(
    test_user, project, organisation, user_project_permission
):
    # Given - another project in the same organisation
    project_two = Project.objects.create(organisation=organisation, name="Project two")

    # and the user has admin permission on the other project
    user_project_permission.admin = True
    user_project_permission.save()

    assert is_user_project_admin(test_user, project_two) is False
