import falcon


class RootResource(object):

    def on_get(self, req, res):
        pass



class Application(falcon.API):

    def __init__(self):
        super().__init__(middleware=[])


    # self.resp_options.media_handlers = falcon.media.Handlers({
    #     'application/json': JSONHandler(app_entity_links),
    # })
    # self.add_route('/', RootResource(
    #     users_repo, sounds_repo, annotations_repo, is_dev_environment))
    # self.add_route('/users', UsersResource(email_whitelist))
    # self.add_route(USER_URI_TEMPLATE, UserResource())
    # self.add_route('/sounds', SoundsResource())
    # self.add_route(SOUND_URI_TEMPLATE, SoundResource())
    # self.add_route(
    #     '/sounds/{sound_id}/annotations', SoundAnnotationsResource())
    # self.add_route('/users/{user_id}/sounds', UserSoundsResource())
    # self.add_route('/users/{user_id}/annotations',
    #                UserAnnotationResource())
    # self.add_route('/annotations', AnnotationsResource())

    # self.add_error_handler(PermissionsError, permissions_error)
    # self.add_error_handler(
    #     CompositeValidationError, composite_validation_error)
    # self.add_error_handler(EntityNotFoundError, not_found_error)

    def add_route(self, route, resource, *args, **kwargs):
        self._doc_routes.append((route, resource))
        super().add_route(route, resource, *args, **kwargs)
