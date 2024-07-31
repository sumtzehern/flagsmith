import React, { FC, ReactNode, useEffect, useRef, useState } from 'react' // we need this to make JSX compile
import { RouterChildContext } from 'react-router'
import { find, sortBy } from 'lodash'

import Constants from 'common/constants'
import useSearchThrottle from 'common/useSearchThrottle'
import { Segment } from 'common/types/responses'
import {
  useDeleteSegmentMutation,
  useGetSegmentsQuery,
} from 'common/services/useSegment'
import { useHasPermission } from 'common/providers/Permission'
import API from 'project/api'
import Button from 'components/base/forms/Button'
import ConfirmRemoveSegment from 'components/modals/ConfirmRemoveSegment'
import CreateSegmentModal from 'components/modals/CreateSegment'
import PanelSearch from 'components/PanelSearch'
import JSONReference from 'components/JSONReference'
import ConfigProvider from 'common/providers/ConfigProvider'
import Utils from 'common/utils/utils'
import ProjectStore from 'common/stores/project-store'
import Icon from 'components/Icon'
import PageTitle from 'components/PageTitle'
import Switch from 'components/Switch'
import { setModalTitle } from 'components/modals/base/ModalDefault'
import classNames from 'classnames'
import InfoMessage from 'components/InfoMessage'

const CodeHelp = require('../../components/CodeHelp')
type SegmentsPageType = {
  router: RouterChildContext['router']
  match: {
    params: {
      environmentId: string
      projectId: string
    }
  }
}

const SegmentsPage: FC<SegmentsPageType> = (props) => {
  const { projectId } = props.match.params
  const environmentId =
    ProjectStore.getEnvironment()?.api_key || 'ENVIRONMENT_API_KEY'
  const preselect = useRef(Utils.fromParam().id)
  const hasNoOperators = !Utils.getFlagsmithValue('segment_operators')

  const { search, searchInput, setSearchInput } = useSearchThrottle('')
  const [page, setPage] = useState(1)
  const [showFeatureSpecific, setShowFeatureSpecific] = useState(false)

  const { data, error, isLoading, refetch } = useGetSegmentsQuery({
    include_feature_specific: showFeatureSpecific,
    page,
    page_size: 100,
    projectId,
    q: search,
  })
  const [removeSegment, { isLoading: isRemoving }] = useDeleteSegmentMutation()

  const segmentsLimitAlert = Utils.calculateRemainingLimitsPercentage(
    ProjectStore.getTotalSegments(),
    ProjectStore.getMaxSegmentsAllowed(),
  )

  useEffect(() => {
    API.trackPage(Constants.pages.FEATURES)
  }, [])
  useEffect(() => {
    if (error) {
      // Kick user back out to projects
      props.router.history.replace(Utils.getOrganisationHomePage())
    }
  }, [error, props.router.history])
  const newSegment = () => {
    openModal(
      'New Segment',
      <CreateSegmentModal
        onComplete={(segment) => {
          //todo: remove when CreateSegment uses hooks
          setModalTitle(`Edit Segment: ${segment.name}`)
          toast('Created segment')
        }}
        environmentId={environmentId}
        projectId={projectId}
      />,
      'side-modal create-new-segment-modal',
    )
  }
  const confirmRemove = (segment: Segment, cb: () => void) => {
    openModal(
      'Remove Segment',
      <ConfirmRemoveSegment segment={segment} cb={cb} />,
      'p-0',
    )
  }

  const { permission: manageSegmentsPermission } = useHasPermission({
    id: projectId,
    level: 'project',
    permission: 'MANAGE_SEGMENTS',
  })

  const editSegment = (id: number, readOnly?: boolean) => {
    API.trackEvent(Constants.events.VIEW_SEGMENT)
    history.replaceState({}, '', `${document.location.pathname}?id=${id}`)

    openModal(
      `Edit Segment`,
      <CreateSegmentModal
        segment={id}
        onSegmentRetrieved={(segment) =>
          setModalTitle(`Edit Segment: ${segment.name}`)
        }
        readOnly={readOnly}
        onComplete={() => {
          refetch()
          toast('Updated Segment')
        }}
        environmentId={environmentId}
        projectId={projectId}
      />,
      'side-modal create-segment-modal',
      () => {
        history.replaceState({}, '', `${document.location.pathname}`)
      },
    )
  }
  const renderWithPermission = (
    permission: boolean,
    name: string,
    el: ReactNode,
  ) => {
    return permission ? (
      el
    ) : (
      <Tooltip title={el} place='right'>
        {Constants.projectPermissions('Manage segments')}
      </Tooltip>
    )
  }
  const segments = data?.results
  return (
    <div
      data-test='segments-page'
      id='segments-page'
      className='app-container container'
    >
      <PageTitle
        cta={
          <>
            {renderWithPermission(
              manageSegmentsPermission,
              'Manage segments',
              <Button
                disabled={
                  !manageSegmentsPermission ||
                  segmentsLimitAlert.percentage >= 100
                }
                id='show-create-segment-btn'
                data-test='show-create-segment-btn'
                onClick={newSegment}
              >
                Create Segment
              </Button>,
            )}
          </>
        }
        title={'Segments'}
      >
        Create and manage groups of users with similar{' '}
        <Button
          theme='text'
          href='https://docs.flagsmith.com/basic-features/managing-identities#identity-traits'
          target='_blank'
        >
          traits
        </Button>
        . Segments can be used to override features within the features page for
        any environment.{' '}
        <Button
          theme='text'
          target='_blank'
          href='https://docs.flagsmith.com/basic-features/segments'
          className='fw-normal'
        >
          Learn more.
        </Button>
      </PageTitle>
      <div className='segments-page'>
        {isLoading && !segments && !searchInput && (
          <div className='centered-container'>
            <Loader />
          </div>
        )}
        {(!isLoading || segments || searchInput) && (
          <div>
            {Utils.displayLimitAlert('segments', segmentsLimitAlert.percentage)}
            <div>
              <FormGroup className={classNames({ 'opacity-50': isRemoving })}>
                <PanelSearch
                  filterElement={
                    <div className='text-right me-2'>
                      <label className='me-2'>Include Feature-Specific</label>
                      <Switch onChange={setShowFeatureSpecific} />
                    </div>
                  }
                  renderSearchWithNoResults
                  className='no-pad'
                  id='segment-list'
                  title=' '
                  renderFooter={() => (
                    <JSONReference
                      className='mx-2 mt-4'
                      title={'Segments'}
                      json={segments}
                    />
                  )}
                  items={sortBy(segments, (v) => {
                    return `${v.feature ? 'a' : 'z'}${v.name}`
                  })}
                  renderRow={(
                    { description, feature, id, name }: Segment,
                    i: number,
                  ) => {
                    if (preselect.current === `${id}`) {
                      editSegment(preselect.current, !manageSegmentsPermission)
                      preselect.current = null
                    }

                    // TODO: remove this check
                    // I'm leaving this here for now so that we can deploy the FE and
                    // API independently, but we should remove this once PR #3430 is
                    // merged and released.
                    if (feature && !showFeatureSpecific) {
                      return null
                    }

                    return renderWithPermission(
                      manageSegmentsPermission,
                      'Manage segments',
                      <Row className='list-item clickable' key={id} space>
                        <Flex
                          className='table-column px-3'
                          onClick={
                            manageSegmentsPermission
                              ? () => editSegment(id, !manageSegmentsPermission)
                              : undefined
                          }
                        >
                          <Row
                            data-test={`segment-${i}-name`}
                            className='font-weight-medium'
                          >
                            {name}
                            {feature && (
                              <div className='chip chip--xs ml-2'>
                                Feature-Specific
                              </div>
                            )}
                          </Row>
                          <div className='list-item-subtitle mt-1'>
                            {description || 'No description'}
                          </div>
                        </Flex>
                        <div className='table-column'>
                          <Button
                            disabled={!manageSegmentsPermission}
                            data-test={`remove-segment-btn-${i}`}
                            onClick={() => {
                              const segment = find(segments, { id })
                              if (segment) {
                                confirmRemove(segment, () => {
                                  removeSegment({ id, projectId }).then(
                                    (res) => {
                                      toast(
                                        <div>
                                          Removed Segment:{' '}
                                          <strong>{segment.name}</strong>
                                        </div>,
                                      )
                                    },
                                  )
                                })
                              }
                            }}
                            className='btn btn-with-icon'
                          >
                            <Icon name='trash-2' width={20} fill='#656D7B' />
                          </Button>
                        </div>
                      </Row>,
                    )
                  }}
                  paging={data}
                  nextPage={() => setPage(page + 1)}
                  prevPage={() => setPage(page - 1)}
                  goToPage={(page: number) => setPage(page)}
                  search={searchInput}
                  onChange={(e: any) => {
                    setSearchInput(Utils.safeParseEventValue(e))
                  }}
                  filterRow={() => true}
                />
              </FormGroup>

              <InfoMessage>
                Segments require you to identitfy users, setting traits will add
                users to segments.
              </InfoMessage>
              <FormGroup className='mt-4'>
                <CodeHelp
                  title='Using segments'
                  snippets={Constants.codeHelp.USER_TRAITS(
                    environmentId || 'ENVIRONMENT_KEY',
                  )}
                />
              </FormGroup>
            </div>
          </div>
        )}
        <FormGroup>
          <CodeHelp
            title='Managing user traits and segments'
            snippets={Constants.codeHelp.USER_TRAITS(environmentId)}
          />
        </FormGroup>
      </div>
    </div>
  )
}

module.exports = ConfigProvider(SegmentsPage)
