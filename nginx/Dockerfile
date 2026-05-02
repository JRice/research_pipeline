FROM nginx:1.25-alpine

# Remove the default config; our template replaces it.
RUN rm /etc/nginx/conf.d/default.conf

# The official nginx image processes /etc/nginx/templates/*.template with
# envsubst at container start, then writes the result to /etc/nginx/conf.d/.
COPY default.conf.template /etc/nginx/templates/default.conf.template
COPY static/ /usr/share/nginx/html/

EXPOSE 80
