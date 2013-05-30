/*jslint browser: true, nomen: true, indent: 4, */
/*global Ext, OpenLayers, mapstory */

(function (global, Ext, OpenLayers, undefined) {
    'use strict';

    Ext.ns('mapstory.annotations');
    Ext.ns('mapstory.annotations.protocol');


    // the annotation protocol supports filtering "features" by
    // map id and by bounding box.

    // we also support editing via a feature manager

    // assume that the current annotation end point supports a restful
    // api.


    // GET /map/:id/annotations/ -> returns a list
    // POST /map/:id/annotations/ -> creates a annotation
    // GET /map/:id/annotations/:id -> returns a single annotation
    // DELETE /map/:id/annotations/:id -> removes an annotation



    mapstory.annotations.Protocol = OpenLayers.Class(OpenLayers.Protocol, {

        initialize: function (options) {
            this.format = options.format;
            this.http = options.http || OpenLayers.Request;
            this.response = options.response || OpenLayers.Protocol.Response;

            if (!options.mapConfig) {
                throw {
                    'name': 'MapstoryError',
                    'message': 'You must provide an map config object'
                };
            }
            this.mapConfig = options.mapConfig;
            this.baseUrl = '/maps/' + this.mapConfig.id + '/annotations';
            OpenLayers.Protocol.prototype.initialize.apply(this, arguments);

        },

        destory: function () {
            OpenLayers.Protocol.prototype.destory.apply(this);
        },

        parseFeatures: function (response) {

        },

        read: function () {
            OpenLayers.Protocol.prototype.read.apply(this, arguments);
            var resp = new this.response({
                requestType: "read"
            });

            resp.priv = this.http.GET({
                url: this.baseUrl,
                callback: this.createCallback(this.readFeatures, resp)
            });

            return resp;

        },

        readFeatures: function (resp) {
            resp.features = [new OpenLayers.Feature.Vector({
                geometry: new OpenLayers.Geometry.Point(40, -74)
            })];
        },

        create: function (feature) {
            var resp = this.http.POST({
                url: this.baseUrl,
                data: feature
            });
            return resp;
        },

        update: function (feature) {
            var resp = this.http.PUT({
                url: this.baseUrl + '/' + feature.id,
                data: feature
            });
            return resp;
        },

        delete: function (feature) {
            var resp = this.http.DELETE({
                url: this.baseUrl + '/' + feature.id
            });
            return resp;
        },

        CLASS_NAME: 'mapstory.annotations.Protocol'

    });

}(window, Ext, OpenLayers));
