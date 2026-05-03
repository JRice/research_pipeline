FROM nginx:1.25-alpine

# Remove the default config; our template replaces it.
RUN rm /etc/nginx/conf.d/default.conf

COPY default.conf.template /etc/nginx/templates/default.conf.template
COPY static/ /usr/share/nginx/html/

EXPOSE 80

# Render the template at startup, substituting only $API_HOST so that
# nginx's own $host/$scheme/etc. variables are left untouched.
CMD ["/bin/sh", "-c", "envsubst '$$API_HOST' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
