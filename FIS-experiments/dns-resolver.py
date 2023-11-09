import dns.resolver
import requests

# Set the Route53 DNS resolver to use
dns_resolver_ip = '127.0.0.1'

# Domain to resolve
domain_to_resolve = 'test.hello-localstack.com'


# Resolve the CNAME record using the specified DNS server
resolver = dns.resolver.Resolver(configure=False)
resolver.nameservers = [dns_resolver_ip]

try:
    cname_record = resolver.query(domain_to_resolve, rdtype=dns.rdatatype.CNAME)
    resolved_domain = str(cname_record[0].target)

    # Construct the full URL with the resolved domain
    resolved_url = f'http://{resolved_domain}:4566/dev/productApi?id=prod-1088'

    # Make an HTTP request to the resolved URL
    response = requests.get(resolved_url)

    # Print the response
    print(response.text)

except dns.resolver.NXDOMAIN:
    print(f"CNAME record not found for {domain_to_resolve}")

except Exception as e:
    print(f"Error: {e}")
