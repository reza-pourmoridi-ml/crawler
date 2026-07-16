main goal:
    form this websites (alibaba safar360 booking flytody), for all airlines
    find lowest price fly for specific pathes and return data like a provider.
    best case scenario: is that all process can be done only using a basic linux without ui server.



todo(R&D):
step 2:
    connect to an llm using postman
    give raw data to it and test if gives you good selectors
    write a pythong script for testing selectors
    create a standard loop embedding llm
    test and debug loop using script and raw data of 5 website
    write an auto test and test whole system for 1 hour
    put it aside if successful, if not find another way

go for architect and normalize the codes.


Alibaba.ir
https://www.alibaba.ir/flights/THR-MHD?adult=1&child=0&infant=0&departing=1405-05-02
https://www.alibaba.ir/international/IKA-ISTALL?adult=1&child=0&infant=0&departing=1405-05-02&flightClass=economy

Flytoday.ir
https://www.flytoday.ir/flight/search?departure=thr,1&arrival=mhd,1&departureDate=2026-07-24&adt=1&chd=0&inf=0&cabin=1&isDomestic=true&isAnyWhere=false
https://www.flytoday.ir/flight/search?departure=thr,1&arrival=ist,1&departureDate=2026-07-24&adt=1&chd=0&inf=0&cabin=1&isAnyWhere=false

Snapptrip.ir
https://www.snapptrip.ir/flights/THR_city/MHD_city?adultCount=1&childCount=0&infantCount=0&departureDate=2026-07-24&source=searchBox&dateType=jalali
https://www.snapptrip.ir/inter-flights/THR_city/IST_city?adultCount=1&childCount=0&infantCount=0&departureDate=2026-07-24&source=searchBox&dateType=jalali&cabinType=ECONOMY


Mrbilit.com
https://mrbilit.com/flights/THR-MHD?departureDate=1405-05-02
https://mrbilit.com/flights/IKA-ISTALL?departureDate=1405-05-02&cabinClass=/P


Ghasedak24.com
https://ghasedak24.com/flights/THR-MHD?departure-date=1405-05-02&adult-count=1&child-count=0&infant-count=0
https://ghasedak24.com/flights/IKA-ISTALL?departure-date=1405-05-02&adult-count=1&child-count=0&infant-count=0&cabin=Y